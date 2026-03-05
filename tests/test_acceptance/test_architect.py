"""
Architect Acceptance Tests — Capsule v0.1
==========================================
Written by the architect. Must be executed WITHOUT MODIFICATION.
If any test fails, fix the implementation, not this file.

Phase 1-5: Must pass NOW (retroactive).
Phase 6:   Must pass after Phase 6 is implemented (forward-looking).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from .conftest import make_evidence_dict


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 1: Data Models                                       ║
# ╚══════════════════════════════════════════════════════════════╝

from core.models.base import ContractRef, ContractMeta
from core.models.enums import ContractType, ContractStatus, CreatedBy


class TestPhase1Models:
    """Verify model construction, validation, and rejection."""

    def test_contract_ref_accepts_range_version(self):
        ref = ContractRef(id="behavior.user_auth", version="1.x")
        assert ref.id == "behavior.user_auth"
        assert ref.version == "1.x"

    def test_contract_ref_accepts_precise_version(self):
        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        assert ref.version == "1.0.0"

    def test_contract_ref_rejects_invalid_version(self):
        with pytest.raises(ValidationError):
            ContractRef(id="task.foo", version="latest")

    def test_contract_meta_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ContractMeta(
                type="role",
                id="role.test",
                version="1.0.0",
                status="active",
                created_by="human",
                created_at="2026-01-01T00:00:00Z",
                dependencies=[],
                validation={"schema": "x.json", "checks": []},
                on_failure={"action": "retry", "max_retries": 3, "severity": "mid"},
                this_field_must_not_exist="rejected",
            )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 2: Contract Registry                                  ║
# ╚══════════════════════════════════════════════════════════════╝

from core.registry import Registry, ResolutionError


class TestPhase2Registry:
    """Verify loading, indexing, version resolution."""

    def test_build_loads_all(self, project_root):
        reg = Registry.build(project_root)
        assert len(reg.load_errors) == 0
        # 3 roles + 1 boundary + 1 interface + 1 behavior + 1 task = 7
        assert len(reg.all_contracts()) == 7

    def test_resolve_precise(self, project_root):
        reg = Registry.build(project_root)
        ref = ContractRef(id="behavior.user_auth", version="1.0.0")
        c = reg.resolve(ref)
        assert c.meta.id == "behavior.user_auth"
        assert c.meta.version == "1.0.0"

    def test_resolve_range(self, project_root):
        reg = Registry.build(project_root)
        ref = ContractRef(id="behavior.user_auth", version="1.x")
        c = reg.resolve(ref)
        assert c.meta.version == "1.0.0"
        assert c.meta.status == ContractStatus.active \
            or c.meta.status == "active"

    def test_resolve_missing_raises(self, project_root):
        reg = Registry.build(project_root)
        ref = ContractRef(id="behavior.nonexistent", version="1.0.0")
        with pytest.raises(ResolutionError):
            reg.resolve(ref)

    def test_boundary_intact(self, project_root):
        reg = Registry.build(project_root)
        assert reg.is_boundary_intact() is True


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 3: State Manager                                      ║
# ╚══════════════════════════════════════════════════════════════╝

from core.state_manager import StateManager


class TestPhase3State:
    """Verify state lifecycle: init, roundtrip, runs, checkpoints, human queue."""

    def test_init_save_load_roundtrip(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")
        assert state.project_id == "test-project"
        assert state.status in ("idle", "init")

        sm.save(state)
        loaded = sm.load()
        assert loaded.project_id == "test-project"

    def test_create_run(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        state, run = sm.create_run(state, ref, "role.coder_backend", "coder_backend")

        assert len(state.run_history) == 1
        assert state.run_history[0].run_id == run.run_id
        assert state.current_task_ref is not None
        assert state.current_task_ref.id == "task.user_auth.login_api"

    def test_checkpoint_restore(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        state, run = sm.create_run(state, ref, "role.coder_backend", "coder")
        sm.save(state)

        ckpt_id = sm.save_checkpoint(state)

        # Mutate state after checkpoint
        state.phase = "mutated_after_checkpoint"
        sm.save(state)

        # Restore must give pre-mutation state
        restored = sm.load_checkpoint(ckpt_id)
        assert restored.phase != "mutated_after_checkpoint"
        assert len(restored.run_history) == 1

    def test_human_queue_lifecycle(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        state, item = sm.enqueue_human(
            state, "run-123", "retry_exceeded",
            "Test failed 3 times", ["approve", "abort"],
        )
        assert state.status == "waiting_human"
        assert len(sm.pending_human_items(state)) == 1

        state = sm.resolve_human(state, item.item_id, "HD-001")
        assert len(sm.pending_human_items(state)) == 0


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 4: Gates (INPUT + OUTPUT)                             ║
# ╚══════════════════════════════════════════════════════════════╝

from core.validator import Validator


class TestPhase4Gates:
    """Verify INPUT GATE pass/fail and OUTPUT GATE pass/halt."""

    def _setup(self, project_root):
        reg = Registry.build(project_root)
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")
        val = Validator(reg, sm)
        return reg, sm, state, val

    # ── INPUT GATE ──

    def test_input_gate_pass(self, project_root):
        _, _, state, val = self._setup(project_root)
        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        result = val.input_gate(state, ref, "role.coder_backend")

        assert result.passed is True
        assert result.rejection is None
        assert len(result.resolved_refs) > 0
        # All resolved refs must be precise (no ".x")
        for r in result.resolved_refs:
            assert "x" not in r.version

    def test_input_gate_missing_role_fails(self, project_root):
        _, _, state, val = self._setup(project_root)
        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        result = val.input_gate(state, ref, "role.nonexistent")

        assert result.passed is False

    # ── OUTPUT GATE ──

    def _setup_for_output(self, project_root):
        reg, sm, state, val = self._setup(project_root)
        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        state, run = sm.create_run(state, ref, "role.coder_backend", "coder_backend")
        state = sm.lock_refs(state, [
            ContractRef(id="task.user_auth.login_api", version="1.0.0"),
            ContractRef(id="behavior.user_auth", version="1.0.0"),
            ContractRef(id="interface.user_auth", version="1.0.0"),
        ])
        sm.save(state)
        return sm, state, val, run

    def test_output_gate_pass(self, project_root):
        sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=["pytest -q tests/backend/"],
        )

        assert result.passed is True
        assert result.halt is False

    def test_output_gate_sacred_file_halt(self, project_root):
        sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["contracts/schemas/evil.json"],
            commands_ran=["pytest"],
        )

        assert result.halt is True
        assert len(result.boundary_violations) > 0

    def test_output_gate_forbidden_command_halt(self, project_root):
        sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=["git push origin main"],
        )

        assert result.halt is True


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 5: Executor Port + Evidence Builder                   ║
# ╚══════════════════════════════════════════════════════════════╝

from core.executor.port import ExecutorPort
from core.executor.evidence_builder import build_evidence
from core.models.execution import ExecutionRequest, ExecutionResult


class TestPhase5Executor:
    """Verify executor abstraction and evidence builder."""

    def test_executor_port_is_abstract(self):
        with pytest.raises(TypeError):
            ExecutorPort()

    def test_build_evidence_produces_valid_dict(self):
        req = ExecutionRequest(
            run_id="20260101-000000-abcdef01",
            role_id="role.coder_backend",
            task_ref=ContractRef(
                id="task.user_auth.login_api", version="1.0.0"
            ),
            working_dir="/tmp/fake",
            allowed_write=["src/backend/**"],
            allowed_exec=["pytest"],
            prohibited_write=["state/**"],
            prohibited_exec=["git push"],
            task_prompt="Implement login",
            injected_context={},
        )
        res = ExecutionResult(
            success=True,
            exit_code=0,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=[
                {"cmd": "codex exec task", "exit_code": 0, "duration_ms": 5000}
            ],
            agent_output="Done",
            error_message=None,
            duration_ms=5000,
        )
        refs = [
            ContractRef(id="behavior.user_auth", version="1.0.0"),
            ContractRef(id="interface.user_auth", version="1.0.0"),
        ]

        ev = build_evidence(req, res, refs)

        assert isinstance(ev, dict)
        assert ev["run_id"] == "20260101-000000-abcdef01"
        assert ev["task_ref"]["id"] == "task.user_auth.login_api"
        assert "changes" in ev
        assert "self_report" in ev

    def test_evidence_from_builder_passes_output_gate_l0(self, project_root):
        """Evidence built by build_evidence must survive OUTPUT GATE L0."""
        reg = Registry.build(project_root)
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")
        val = Validator(reg, sm)

        task_ref = ContractRef(
            id="task.user_auth.login_api", version="1.0.0"
        )
        state, run = sm.create_run(
            state, task_ref, "role.coder_backend", "coder_backend"
        )
        state = sm.lock_refs(state, [
            ContractRef(id="task.user_auth.login_api", version="1.0.0"),
            ContractRef(id="behavior.user_auth", version="1.0.0"),
            ContractRef(id="interface.user_auth", version="1.0.0"),
        ])
        sm.save(state)

        req = ExecutionRequest(
            run_id=run.run_id,
            role_id="role.coder_backend",
            task_ref=task_ref,
            working_dir="/tmp/fake",
            allowed_write=["src/backend/**"],
            allowed_exec=["pytest"],
            prohibited_write=["state/**"],
            prohibited_exec=["git push"],
            task_prompt="Implement login",
            injected_context={},
        )
        res = ExecutionResult(
            success=True,
            exit_code=0,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=[
                {"cmd": "codex exec task", "exit_code": 0, "duration_ms": 5000}
            ],
            agent_output="Done",
            error_message=None,
            duration_ms=5000,
        )
        refs = [
            ContractRef(id="task.user_auth.login_api", version="1.0.0"),
            ContractRef(id="behavior.user_auth", version="1.0.0"),
            ContractRef(id="interface.user_auth", version="1.0.0"),
        ]

        ev = build_evidence(req, res, refs)

        result = val.output_gate(
            state, run.run_id, ev,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=["pytest"],
        )

        # Must not fail at L0 (schema validation)
        # It may or may not pass overall depending on L1/L2/L3,
        # but the gate_report must exist and level must be > 0 if it failed
        assert result is not None
        if not result.passed:
            report = result.gate_report
            # If it failed, it must NOT be L0 (evidence format)
            assert report.get("spec", report).get("level", -1) != 0


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 6: L2 Behavior Verification (FORWARD-LOOKING)        ║
# ║                                                              ║
# ║  These tests WILL FAIL until Phase 6 is implemented.         ║
# ║  After implementation, ALL tests in this file must pass.     ║
# ╚══════════════════════════════════════════════════════════════╝


class TestPhase6L2:
    """Verify L2 behavior verification in OUTPUT GATE."""

    def _setup_for_output(self, project_root):
        reg = Registry.build(project_root)
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")
        val = Validator(reg, sm)

        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        state, run = sm.create_run(state, task_ref, "role.coder_backend", "coder_backend")
        state = sm.lock_refs(state, [
            ContractRef(id="task.user_auth.login_api", version="1.0.0"),
            ContractRef(id="behavior.user_auth", version="1.0.0"),
            ContractRef(id="interface.user_auth", version="1.0.0"),
        ])
        sm.save(state)
        return reg, sm, state, val, run

    def test_l2_pass_with_passing_tests(self, project_root):
        """When test_runner reports passed=True, L2 should pass."""
        from core.test_runner import TestRunner, TestResult

        reg, sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        mock_runner = MagicMock(spec=TestRunner)
        mock_runner.run.return_value = TestResult(
            passed=True,
            exit_code=0,
            command="pytest -q tests/backend/test_user_auth.py",
            stdout="12 passed",
            stderr="",
            duration_ms=1200,
            summary="All tests passed",
            error_details=[],
        )

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=["pytest"],
            test_runner=mock_runner,
            working_dir=str(project_root),
        )

        assert result.passed is True
        assert result.halt is False
        assert result.l2_result is not None
        assert result.l2_result["status"] == "passed"

    def test_l2_fail_produces_rejection(self, project_root):
        """When test_runner reports passed=False, L2 should fail with rejection."""
        from core.test_runner import TestRunner, TestResult

        reg, sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        mock_runner = MagicMock(spec=TestRunner)
        mock_runner.run.return_value = TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_user_auth.py",
            stdout="11 passed, 1 failed",
            stderr="FAILED test_jwt_format - AssertionError",
            duration_ms=1500,
            summary="11 passed, 1 failed",
            error_details=["FAILED test_jwt_format - AssertionError"],
        )

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=["pytest"],
            test_runner=mock_runner,
            working_dir=str(project_root),
        )

        assert result.passed is False
        assert result.halt is False  # L2 fail is rejection, not halt
        assert result.rejection is not None
        assert result.l2_result is not None
        assert result.l2_result["status"] == "failed"

    def test_l2_fail_does_not_skip_l3(self, project_root):
        """Even if L2 fails, L3 must still execute. L3 halt takes priority."""
        from core.test_runner import TestRunner, TestResult

        reg, sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        mock_runner = MagicMock(spec=TestRunner)
        mock_runner.run.return_value = TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_user_auth.py",
            stdout="1 failed",
            stderr="FAILED test_foo",
            duration_ms=500,
            summary="1 failed",
            error_details=["FAILED test_foo"],
        )

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["contracts/schemas/evil.json"],  # sacred file!
            commands_ran=["pytest"],
            test_runner=mock_runner,
            working_dir=str(project_root),
        )

        # L3 must trigger halt even though L2 also failed
        assert result.halt is True
        assert len(result.boundary_violations) > 0
        # L2 result must still be recorded
        assert result.l2_result is not None
        assert result.l2_result["status"] == "failed"

    def test_l2_skipped_when_no_runner(self, project_root):
        """Without test_runner, L2 must be skipped (backward compat with Phase 4)."""
        reg, sm, state, val, run = self._setup_for_output(project_root)
        evidence = make_evidence_dict(run.run_id)

        result = val.output_gate(
            state, run.run_id, evidence,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=["pytest"],
            # no test_runner, no working_dir
        )

        assert result.passed is True
        assert result.halt is False
        if result.l2_result is not None:
            assert result.l2_result["status"] == "skipped"


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 7: Lean Orchestrator                                  ║
# ╚══════════════════════════════════════════════════════════════╝

from core.models.workflow import WorkflowDef, WorkflowNode
from core.orchestrator import Orchestrator, OrchestratorResult
from core.test_runner import TestRunner, TestResult
from core.prompt_builder import build_prompt


class TestPhase7Orchestrator:
    """Verify orchestrator: single-node pass, retry+breaker, halt, resume."""

    def _build_orchestrator(self, project_root, mock_executor, mock_test_runner=None):
        reg = Registry.build(project_root)
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")
        sm.save(state)
        val = Validator(reg, sm)
        tr = mock_test_runner or MagicMock(spec=TestRunner)
        if mock_test_runner is None:
            tr.run.return_value = TestResult(
                passed=True, exit_code=0,
                command="pytest -q", stdout="ok", stderr="",
                duration_ms=100, summary="All tests passed",
                error_details=[],
            )
        orch = Orchestrator(
            registry=reg,
            state_manager=sm,
            validator=val,
            executor=mock_executor,
            test_runner=tr,
            project_root=project_root,
        )
        return orch, sm

    def _make_exec_result(self, success=True):
        return ExecutionResult(
            success=success,
            exit_code=0 if success else 1,
            modified_files=["src/backend/auth/login.py"],
            commands_ran=[
                {"cmd": "codex exec task", "exit_code": 0 if success else 1, "duration_ms": 3000}
            ],
            agent_output="Done" if success else "Failed",
            error_message=None if success else "execution failed",
            duration_ms=3000,
        )

    def _single_node_workflow(self):
        return WorkflowDef(
            id="workflow.test_single",
            nodes=[WorkflowNode(
                id="coder_backend",
                role="role.coder_backend",
                action="implement",
                human_review=False,
            )],
        )

    def _single_node_with_review(self):
        return WorkflowDef(
            id="workflow.test_review",
            nodes=[WorkflowNode(
                id="coder_backend",
                role="role.coder_backend",
                action="implement",
                human_review=True,
            )],
        )

    def test_single_node_pass(self, project_root):
        """One node, executor succeeds, tests pass → completed."""
        mock_exec = MagicMock(spec=ExecutorPort)
        mock_exec.execute.return_value = self._make_exec_result(success=True)

        orch, sm = self._build_orchestrator(project_root, mock_exec)
        wf = self._single_node_workflow()
        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")

        result = orch.run(wf, task_ref)

        assert result.status == "completed"
        assert result.runs_executed >= 1

        state = sm.load()
        assert state.status == "completed"

    def test_retry_then_pass(self, project_root):
        """First attempt fails L2, second succeeds → completed."""
        mock_exec = MagicMock(spec=ExecutorPort)
        mock_exec.execute.return_value = self._make_exec_result(success=True)

        fail_result = TestResult(
            passed=False, exit_code=1,
            command="pytest -q", stdout="1 failed", stderr="FAILED test_x",
            duration_ms=100, summary="1 failed",
            error_details=["FAILED test_x"],
        )
        pass_result = TestResult(
            passed=True, exit_code=0,
            command="pytest -q", stdout="ok", stderr="",
            duration_ms=100, summary="All tests passed",
            error_details=[],
        )
        mock_tr = MagicMock(spec=TestRunner)
        mock_tr.run.side_effect = [fail_result, pass_result]

        orch, sm = self._build_orchestrator(project_root, mock_exec, mock_tr)
        wf = self._single_node_workflow()
        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")

        result = orch.run(wf, task_ref)

        assert result.status == "completed"
        assert mock_exec.execute.call_count == 2

    def test_breaker_triggers_human(self, project_root):
        """All retries exhausted → waiting_human."""
        mock_exec = MagicMock(spec=ExecutorPort)
        mock_exec.execute.return_value = self._make_exec_result(success=True)

        fail_result = TestResult(
            passed=False, exit_code=1,
            command="pytest -q", stdout="fail", stderr="FAILED",
            duration_ms=100, summary="failed",
            error_details=["FAILED"],
        )
        mock_tr = MagicMock(spec=TestRunner)
        mock_tr.run.return_value = fail_result  # always fails

        orch, sm = self._build_orchestrator(project_root, mock_exec, mock_tr)
        wf = self._single_node_workflow()
        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")

        result = orch.run(wf, task_ref)

        assert result.status == "waiting_human"
        assert len(result.human_items) > 0

        state = sm.load()
        assert state.status == "waiting_human"

    def test_human_review_node_pauses(self, project_root):
        """Node with human_review=True → waiting_human after pass."""
        mock_exec = MagicMock(spec=ExecutorPort)
        mock_exec.execute.return_value = self._make_exec_result(success=True)

        orch, sm = self._build_orchestrator(project_root, mock_exec)
        wf = self._single_node_with_review()
        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")

        result = orch.run(wf, task_ref)

        assert result.status == "waiting_human"
        assert result.current_node_id == "coder_backend"

    def test_resume_after_human_decision(self, project_root):
        """After human resolves queue, resume continues workflow."""
        mock_exec = MagicMock(spec=ExecutorPort)
        mock_exec.execute.return_value = self._make_exec_result(success=True)

        orch, sm = self._build_orchestrator(project_root, mock_exec)
        wf = self._single_node_with_review()
        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")

        # First run pauses at human review
        result1 = orch.run(wf, task_ref)
        assert result1.status == "waiting_human"

        # Simulate human decision
        state = sm.load()
        for item in sm.pending_human_items(state):
            state = sm.resolve_human(state, item.item_id, "HD-test-001")
        sm.save(state)

        # Resume should complete
        result2 = orch.resume(wf)
        assert result2.status == "completed"

    def test_prompt_builder_produces_string(self, project_root):
        """build_prompt must return a non-empty string."""
        reg = Registry.build(project_root)

        task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        task_c = reg.resolve(task_ref)

        behavior_ref = ContractRef(id="behavior.user_auth", version="1.0.0")
        behavior_c = reg.resolve(behavior_ref)

        interface_ref = ContractRef(id="interface.user_auth", version="1.0.0")
        interface_c = reg.resolve(interface_ref)

        role_c = reg.get_latest_active("role.coder_backend")

        node = WorkflowNode(
            id="coder_backend",
            role="role.coder_backend",
            action="implement",
        )

        prompt = build_prompt(
            node=node,
            task_contract=task_c.model_dump() if hasattr(task_c, "model_dump") else task_c,
            interface_contracts=[interface_c.model_dump() if hasattr(interface_c, "model_dump") else interface_c],
            behavior_contract=behavior_c.model_dump() if hasattr(behavior_c, "model_dump") else behavior_c,
            role_contract=role_c.model_dump() if hasattr(role_c, "model_dump") else role_c,
            state_snapshot={"project_id": "test", "phase": "development"},
            rejection_history=None,
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        # Must contain key contract info
        assert "user_auth" in prompt
        assert "coder_backend" in prompt.lower() or "Backend Coder" in prompt


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 8: Human Loop + CLI                                   ║
# ╚══════════════════════════════════════════════════════════════╝

from core.human_loop import HumanLoop, ReviewSummary
from core.models.config import CapsuleConfig


class TestPhase8HumanLoop:
    """Verify human loop: review generation, formatting, decision application."""

    def test_pending_reviews_from_queue(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        state, item = sm.enqueue_human(
            state, "run-001", "retry_exceeded",
            "Task failed after 3 retries",
            ["approve", "amend_contract", "pause", "abort"],
        )
        sm.save(state)

        hl = HumanLoop(sm)
        reviews = hl.get_pending_reviews(state)

        assert len(reviews) == 1
        assert isinstance(reviews[0], ReviewSummary)
        assert reviews[0].item_id == item.item_id
        assert reviews[0].trigger == "retry_exceeded"
        assert "approve" in reviews[0].options

    def test_format_review_produces_readable_text(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        state, item = sm.enqueue_human(
            state, "run-001", "review_required",
            "Node completed, awaiting review",
            ["approve", "abort"],
        )
        sm.save(state)

        hl = HumanLoop(sm)
        reviews = hl.get_pending_reviews(state)
        text = hl.format_review(reviews[0])

        assert isinstance(text, str)
        assert len(text) > 50
        assert "approve" in text
        assert "abort" in text
        assert item.item_id in text

    def test_apply_decision_resolves_item(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
        state, run = sm.create_run(state, ref, "role.coder_backend", "coder_backend")

        state, item = sm.enqueue_human(
            state, run.run_id, "retry_exceeded",
            "Failed", ["approve", "abort"],
        )
        sm.save(state)

        hl = HumanLoop(sm)
        state = hl.apply_decision(state, item.item_id, "approve", "Looks good")
        sm.save(state)

        assert len(sm.pending_human_items(state)) == 0

        # HumanDecision file must exist
        run_dir = sm.run_dir(run.run_id)
        hd_dir = run_dir / "human_decisions"
        assert hd_dir.exists()
        hd_files = list(hd_dir.iterdir())
        assert len(hd_files) >= 1

    def test_apply_decision_rejects_invalid_option(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        state, item = sm.enqueue_human(
            state, "run-001", "review_required",
            "Review", ["approve", "abort"],
        )
        sm.save(state)

        hl = HumanLoop(sm)
        with pytest.raises(Exception):
            # "invalid_option" is not in the presented options
            hl.apply_decision(state, item.item_id, "invalid_option", "")


class TestPhase8Config:
    """Verify capsule.yaml loading."""

    def test_config_loads_from_yaml(self, project_root):
        config_path = project_root / "capsule.yaml"
        config_path.write_text(
            "capsule:\n"
            "  project_id: test-project\n"
            "  workflow: workflows/standard.yaml\n"
        )

        import yaml
        with open(config_path) as f:
            raw = yaml.safe_load(f)

        data = raw.get("capsule", raw)
        config = CapsuleConfig(**data)

        assert config.project_id == "test-project"
        assert config.workflow == "workflows/standard.yaml"

    def test_config_rejects_extra_fields(self, project_root):
        with pytest.raises(ValidationError):
            CapsuleConfig(
                project_id="test",
                workflow="w.yaml",
                unknown_field="bad",
            )


class TestPhase8CLI:
    """Verify CLI dispatches correctly (unit-level, not subprocess)."""

    def test_cli_module_importable(self):
        """core.cli must be importable and have a main function."""
        from core.cli import main
        assert callable(main)

    def test_cli_status_on_initialized_project(self, project_root):
        """After init, capsule status should work without error."""
        # Initialize
        sm = StateManager(project_root / "state")
        sm.init_project("test-project")

        # Write minimal capsule.yaml
        config_path = project_root / "capsule.yaml"
        config_path.write_text(
            "capsule:\n"
            "  project_id: test-project\n"
            "  workflow: workflows/standard.yaml\n"
        )

        # CLI status should be callable
        # We test by importing the function that status would call
        from core.human_loop import HumanLoop
        state = sm.load()
        hl = HumanLoop(sm)
        reviews = hl.get_pending_reviews(state)
        assert isinstance(reviews, list)


# ╔══════════════════════════════════════════════════════════════╗
# ║  Phase 8b: Scaffold + Polish                                 ║
# ╚══════════════════════════════════════════════════════════════╝

from core.scaffold import scaffold_project, ScaffoldReport
from core.validate_project import validate_project, ValidationIssue


class TestPhase8bScaffold:
    """Verify scaffold generates complete, valid project."""

    def test_scaffold_creates_all_files(self, tmp_path):
        report = scaffold_project(tmp_path, "test-project")

        assert isinstance(report, ScaffoldReport)
        assert len(report.errors) == 0
        assert len(report.created) > 0

        # Core files must exist
        assert (tmp_path / "capsule.yaml").exists()
        assert (tmp_path / ".gitignore").exists()
        assert (tmp_path / "CAPSULE.md").exists()
        assert (tmp_path / "roles" / "architect.contract.yaml").exists()
        assert (tmp_path / "roles" / "qa.contract.yaml").exists()
        assert (tmp_path / "roles" / "coder_backend.contract.yaml").exists()
        assert (tmp_path / "workflows" / "standard.yaml").exists()
        assert (tmp_path / "contracts" / "boundaries" / "global.boundary.yaml").exists()
        assert (tmp_path / "contracts" / "schemas").is_dir()
        assert (tmp_path / "prompts" / "architect.md").exists()
        assert (tmp_path / "prompts" / "qa.md").exists()
        assert (tmp_path / "prompts" / "coder.md").exists()

    def test_scaffold_idempotent(self, tmp_path):
        report1 = scaffold_project(tmp_path, "test-project")
        report2 = scaffold_project(tmp_path, "test-project")

        # Second run should skip everything
        assert len(report2.created) == 0
        assert len(report2.skipped) == len(report1.created)
        assert len(report2.errors) == 0

    def test_scaffold_produces_valid_contracts(self, tmp_path):
        scaffold_project(tmp_path, "test-project")

        # Registry must load all scaffolded contracts without error
        reg = Registry.build(tmp_path)
        assert len(reg.load_errors) == 0
        assert reg.is_boundary_intact() is True
        # At least: 3 roles + 1 boundary = 4
        assert len(reg.all_contracts()) >= 4

    def test_scaffold_schemas_exported(self, tmp_path):
        scaffold_project(tmp_path, "test-project")

        schemas_dir = tmp_path / "contracts" / "schemas"
        schema_files = list(schemas_dir.glob("*.json"))
        # Must have at least the core schemas
        assert len(schema_files) >= 5


class TestPhase8bValidate:
    """Verify project validation catches real problems."""

    def test_valid_project_no_issues(self, tmp_path):
        scaffold_project(tmp_path, "test-project")
        # Also init state
        sm = StateManager(tmp_path / "state")
        sm.init_project("test-project")

        issues = validate_project(tmp_path)
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0

    def test_missing_capsule_yaml(self, tmp_path):
        # Empty dir — no capsule.yaml
        issues = validate_project(tmp_path)
        errors = [i for i in issues if i.level == "error"]
        assert any("capsule.yaml" in e.message for e in errors)

    def test_missing_boundary(self, tmp_path):
        scaffold_project(tmp_path, "test-project")
        sm = StateManager(tmp_path / "state")
        sm.init_project("test-project")
        # Delete boundary
        import shutil

        shutil.rmtree(tmp_path / "contracts" / "boundaries")
        (tmp_path / "contracts" / "boundaries").mkdir()

        issues = validate_project(tmp_path)
        errors = [i for i in issues if i.level == "error"]
        assert any("boundary" in e.message.lower() for e in errors)

    def test_workflow_references_missing_role(self, tmp_path):
        scaffold_project(tmp_path, "test-project")
        sm = StateManager(tmp_path / "state")
        sm.init_project("test-project")

        # Add a workflow node referencing a role that doesn't exist
        import yaml

        wf_path = tmp_path / "workflows" / "standard.yaml"
        with open(wf_path) as f:
            wf = yaml.safe_load(f)
        wf["workflow"]["nodes"].append(
            {
                "id": "ghost",
                "role": "role.nonexistent",
                "action": "implement",
            }
        )
        with open(wf_path, "w") as f:
            yaml.dump(wf, f)

        issues = validate_project(tmp_path)
        errors = [i for i in issues if i.level == "error"]
        assert any("role.nonexistent" in e.message for e in errors)


class TestPhase8bCLIPolish:
    """Verify CLI improvements."""

    def test_decide_accepts_numeric_option(self, project_root):
        sm = StateManager(project_root / "state")
        state = sm.init_project("test-project")

        state, item = sm.enqueue_human(
            state, "run-001", "review_required",
            "Review", ["approve", "amend_contract", "abort"],
        )
        sm.save(state)

        hl = HumanLoop(sm)

        # Option "1" should map to "approve" (1-based index)
        state = hl.apply_decision(state, item.item_id, "1", "using numeric")
        sm.save(state)

        assert len(sm.pending_human_items(state)) == 0
