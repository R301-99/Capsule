from __future__ import annotations

from unittest.mock import MagicMock

from core.executor.evidence_builder import build_evidence
from core.executor.port import ExecutorPort
from core.models.base import ContractRef
from core.models.evidence import CommandRecord, ExecutionEvidenceSpec
from core.models.enums import GateLevel
from core.models.enums import ContractStatus
from core.models.execution import ExecutionRequest, ExecutionResult
from core.models.state import ProjectStatus
from core.models.workflow import WorkflowDef, WorkflowNode
from core.orchestrator import Orchestrator
from core.human_loop import HumanLoop
from core.registry import Registry
from core.scaffold import scaffold_project
from core.state_manager import StateManager
from core.test_runner import TestResult
from core.validate_project import validate_project
from core.validator import Validator


def _prepare_run(micro_project: dict):
    registry = micro_project["registry"]
    state_manager = micro_project["state_manager"]
    validator = micro_project["validator"]
    state = micro_project["state"]

    task_contract = registry.resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)
    state, run = state_manager.create_run(state, task_ref, "role.coder_backend", "coder_backend")
    input_result = validator.input_gate(state, task_ref, "role.coder_backend")
    assert input_result.passed is True
    state_manager.lock_refs(state, input_result.resolved_refs)
    micro_project["state"] = state
    return state, run, input_result.resolved_refs


def _valid_evidence(run_id: str, task_ref: ContractRef, snapshot_refs: list[ContractRef]) -> dict:
    command_record = {"cmd": "pytest -q tests/backend/test_auth.py", "exit_code": 0, "duration_ms": 100}
    return {
        "run_id": run_id,
        "role_id": "role.coder_backend",
        "task_ref": {"id": task_ref.id, "version": task_ref.version},
        "contract_snapshot": {"refs": [ref.model_dump(mode="json") for ref in snapshot_refs]},
        "changes": {"modified_files": ["src/backend/auth.py"], "diff_stat": {"files": 1, "insertions": 2, "deletions": 1}},
        "commands": {"ran": [command_record]},
        "tests": {"ran": [command_record], "summary": "pass"},
        "self_report": {"confidence": 0.9, "risks": [], "notes": "ok"},
    }


def _build_request(run_id: str, task_ref: ContractRef, project_root: str) -> ExecutionRequest:
    return ExecutionRequest(
        run_id=run_id,
        role_id="role.coder_backend",
        task_ref=task_ref,
        working_dir=project_root,
        allowed_write=["src/**", "contracts/**"],
        allowed_exec=["pytest", "python"],
        prohibited_write=["state/**", "contracts/schemas/**"],
        prohibited_exec=["git push"],
        task_prompt="implement task",
        injected_context={"source": "integration-test"},
        timeout_seconds=30,
    )


def test_1_registry_loads_all_contracts(micro_project: dict) -> None:
    registry = micro_project["registry"]

    assert not registry.load_errors
    assert len(registry.all_contracts()) == 5


def test_2_boundary_intact(micro_project: dict) -> None:
    assert micro_project["registry"].is_boundary_intact() is True


def test_3_resolve_range_ref(micro_project: dict) -> None:
    resolved = micro_project["registry"].resolve(ContractRef(id="behavior.user_auth", version="1.x"))

    assert resolved.meta.version == "1.0.0"
    assert resolved.meta.status == ContractStatus.ACTIVE


def test_4_state_init_and_roundtrip(micro_project: dict) -> None:
    state_manager = micro_project["state_manager"]
    state = micro_project["state"]
    state.phase = "development"

    state_manager.save(state)
    loaded = state_manager.load()

    assert loaded.model_dump(mode="json") == state.model_dump(mode="json")


def test_5_create_run_with_resolved_ref(micro_project: dict) -> None:
    registry = micro_project["registry"]
    state_manager = micro_project["state_manager"]
    state = micro_project["state"]

    task_contract = registry.resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)
    state, run = state_manager.create_run(state, task_ref, "role.coder_backend", "coder_backend")
    micro_project["state"] = state

    assert state_manager.run_dir(run.run_id).exists()
    assert len(state.run_history) == 1
    assert state.current_task_ref is not None
    assert state.current_task_ref.id == task_ref.id
    assert state.current_task_ref.version == task_ref.version


def test_6_checkpoint_preserves_run_history(micro_project: dict) -> None:
    state_manager = micro_project["state_manager"]
    state, _, _ = _prepare_run(micro_project)
    checkpoint_id = state_manager.save_checkpoint(state)
    checkpoint_size = len(state.run_history)

    state.run_history.clear()
    loaded = state_manager.load_checkpoint(checkpoint_id)

    assert len(loaded.run_history) == checkpoint_size


def test_7_input_gate_pass_on_valid_project(micro_project: dict) -> None:
    result = micro_project["validator"].input_gate(
        state=micro_project["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is True
    assert result.rejection is None


def test_8_output_gate_halt_on_sacred_file(micro_project: dict) -> None:
    state, run, locked_refs = _prepare_run(micro_project)

    result = micro_project["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["contracts/schemas/foo.json"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.halt is True
    assert result.boundary_violations


def test_9_output_gate_halt_on_forbidden_command(micro_project: dict) -> None:
    state, run, locked_refs = _prepare_run(micro_project)

    result = micro_project["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["git push origin main"],
    )

    assert result.halt is True
    assert any("prohibited" in item.lower() for item in result.boundary_violations)


def test_10_executor_port_contract(micro_project: dict) -> None:
    class MockExecutor(ExecutorPort):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                success=True,
                exit_code=0,
                modified_files=["src/backend/auth.py"],
                commands_ran=[CommandRecord(cmd="pytest -q tests/backend/test_auth.py", exit_code=0, duration_ms=20)],
                agent_output="ok",
                duration_ms=20,
            )

    state, run, locked_refs = _prepare_run(micro_project)
    request = _build_request(run.run_id, run.task_ref, str(micro_project["project_root"]))
    result = MockExecutor().execute(request)
    evidence = build_evidence(request, result, locked_refs)

    parsed = ExecutionEvidenceSpec(**evidence)
    assert parsed.run_id == run.run_id
    assert parsed.task_ref.version == run.task_ref.version
    assert parsed.tests.summary.value == "pass"


def test_11_evidence_passes_output_gate_l0(micro_project: dict) -> None:
    class MockExecutor(ExecutorPort):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                success=True,
                exit_code=0,
                modified_files=["src/backend/auth.py"],
                commands_ran=[CommandRecord(cmd="pytest -q tests/backend/test_auth.py", exit_code=0, duration_ms=20)],
                agent_output="ok",
                duration_ms=20,
            )

    state, run, locked_refs = _prepare_run(micro_project)
    request = _build_request(run.run_id, run.task_ref, str(micro_project["project_root"]))
    result = MockExecutor().execute(request)
    evidence = build_evidence(request, result, locked_refs)

    output = micro_project["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=evidence,
        modified_files=result.modified_files,
        commands_ran=[item.cmd for item in result.commands_ran],
    )
    assert output.gate_report["level"] != 0


def test_12_l2_pass_with_mock_test_runner(micro_project: dict) -> None:
    class MockRunner:
        def run(self, command, working_dir):
            return TestResult(
                passed=True,
                exit_code=0,
                command=command,
                stdout="12 passed",
                stderr="",
                duration_ms=140,
                summary="All tests passed",
                error_details=[],
            )

    state, run, locked_refs = _prepare_run(micro_project)
    evidence = _valid_evidence(run.run_id, run.task_ref, locked_refs)
    output = micro_project["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=evidence,
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
        test_runner=MockRunner(),
        working_dir=str(micro_project["project_root"]),
    )

    assert output.passed is True
    assert output.l2_result is not None
    assert output.l2_result["status"] == "passed"


def test_13_l2_fail_produces_rejection(micro_project: dict) -> None:
    class MockRunner:
        def run(self, command, working_dir):
            return TestResult(
                passed=False,
                exit_code=1,
                command=command,
                stdout="11 passed, 1 failed",
                stderr="FAILED tests/backend/test_auth.py::test_login",
                duration_ms=180,
                summary="11 passed, 1 failed",
                error_details=["FAILED tests/backend/test_auth.py::test_login"],
            )

    state, run, locked_refs = _prepare_run(micro_project)
    evidence = _valid_evidence(run.run_id, run.task_ref, locked_refs)
    output = micro_project["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=evidence,
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
        test_runner=MockRunner(),
        working_dir=str(micro_project["project_root"]),
    )

    assert output.passed is False
    assert output.halt is False
    assert output.rejection is not None
    assert output.rejection.failed_level == GateLevel.L2


def test_14_orchestrator_single_node_e2e(micro_project: dict) -> None:
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_executor.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=["src/backend/auth.py"],
        commands_ran=[CommandRecord(cmd="codex exec task", exit_code=0, duration_ms=20)],
        agent_output="ok",
        duration_ms=20,
    )
    mock_runner = MagicMock()
    mock_runner.run.return_value = TestResult(
        passed=True,
        exit_code=0,
        command="pytest -q tests/backend/test_auth.py",
        stdout="ok",
        stderr="",
        duration_ms=30,
        summary="All tests passed",
        error_details=[],
    )

    orchestrator = Orchestrator(
        registry=micro_project["registry"],
        state_manager=micro_project["state_manager"],
        validator=micro_project["validator"],
        executor=mock_executor,
        test_runner=mock_runner,
        project_root=micro_project["project_root"],
    )
    workflow = WorkflowDef(
        id="workflow.integration.single",
        nodes=[WorkflowNode(id="coder_backend", role="role.coder_backend", action="implement", human_review=False)],
    )
    task_contract = micro_project["registry"].resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)

    result = orchestrator.run(workflow, task_ref)

    assert result.status == "completed"
    state = micro_project["state_manager"].load()
    assert state.status == ProjectStatus.COMPLETED


def test_15_orchestrator_breaker_then_resume(micro_project: dict) -> None:
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_executor.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=["src/backend/auth.py"],
        commands_ran=[CommandRecord(cmd="codex exec task", exit_code=0, duration_ms=20)],
        agent_output="ok",
        duration_ms=20,
    )
    mock_runner = MagicMock()
    mock_runner.run.side_effect = [
        TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_auth.py",
            stdout="1 failed",
            stderr="FAILED test_auth.py::test_login",
            duration_ms=30,
            summary="1 failed",
            error_details=["FAILED test_auth.py::test_login"],
        ),
        TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_auth.py",
            stdout="1 failed",
            stderr="FAILED test_auth.py::test_login",
            duration_ms=30,
            summary="1 failed",
            error_details=["FAILED test_auth.py::test_login"],
        ),
        TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_auth.py",
            stdout="1 failed",
            stderr="FAILED test_auth.py::test_login",
            duration_ms=30,
            summary="1 failed",
            error_details=["FAILED test_auth.py::test_login"],
        ),
        TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_auth.py",
            stdout="1 failed",
            stderr="FAILED test_auth.py::test_login",
            duration_ms=30,
            summary="1 failed",
            error_details=["FAILED test_auth.py::test_login"],
        ),
        TestResult(
            passed=True,
            exit_code=0,
            command="pytest -q tests/backend/test_auth.py",
            stdout="ok",
            stderr="",
            duration_ms=30,
            summary="All tests passed",
            error_details=[],
        ),
    ]

    orchestrator = Orchestrator(
        registry=micro_project["registry"],
        state_manager=micro_project["state_manager"],
        validator=micro_project["validator"],
        executor=mock_executor,
        test_runner=mock_runner,
        project_root=micro_project["project_root"],
    )
    workflow = WorkflowDef(
        id="workflow.integration.breaker",
        nodes=[
            WorkflowNode(id="coder_backend", role="role.coder_backend", action="implement", human_review=False),
        ],
    )
    task_contract = micro_project["registry"].resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)

    result1 = orchestrator.run(workflow, task_ref)
    assert result1.status == "waiting_human"

    state = micro_project["state_manager"].load()
    for item in micro_project["state_manager"].pending_human_items(state):
        state = micro_project["state_manager"].resolve_human(state, item.item_id, "HD-integration-001")
    micro_project["state_manager"].save(state)

    result2 = orchestrator.resume(workflow)
    assert result2.status == "completed"


def test_16_full_e2e_run_review_decide_resume(micro_project: dict) -> None:
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_executor.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=["src/backend/auth.py"],
        commands_ran=[CommandRecord(cmd="codex exec task", exit_code=0, duration_ms=20)],
        agent_output="ok",
        duration_ms=20,
    )
    mock_runner = MagicMock()
    mock_runner.run.return_value = TestResult(
        passed=True,
        exit_code=0,
        command="pytest -q tests/backend/test_auth.py",
        stdout="ok",
        stderr="",
        duration_ms=30,
        summary="All tests passed",
        error_details=[],
    )

    orchestrator = Orchestrator(
        registry=micro_project["registry"],
        state_manager=micro_project["state_manager"],
        validator=micro_project["validator"],
        executor=mock_executor,
        test_runner=mock_runner,
        project_root=micro_project["project_root"],
    )
    workflow = WorkflowDef(
        id="workflow.integration.full_e2e",
        nodes=[
            WorkflowNode(id="coder_backend", role="role.coder_backend", action="implement", human_review=True),
        ],
    )
    task_contract = micro_project["registry"].resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)

    result1 = orchestrator.run(workflow, task_ref)
    assert result1.status == "waiting_human"

    sm = micro_project["state_manager"]
    state = sm.load()
    hl = HumanLoop(sm)
    pending = hl.get_pending_reviews(state)
    assert len(pending) == 1
    state = hl.apply_decision(state, pending[0].item_id, "approve", "Ship it")
    sm.save(state)

    result2 = orchestrator.resume(workflow)
    assert result2.status == "completed"

    final_state = sm.load()
    assert final_state.status == ProjectStatus.COMPLETED
    run = final_state.run_history[-1]
    decision_dir = sm.run_dir(run.run_id) / "human_decisions"
    assert decision_dir.exists()
    assert any(decision_dir.iterdir())


def test_17_scaffold_then_validate_then_run(tmp_path) -> None:
    project_root = tmp_path / "scaffolded_project"
    report = scaffold_project(project_root, "test-project")
    assert report.errors == []

    sm = StateManager(project_root / "state")
    sm.init_project("test-project")

    import yaml

    now = "2026-03-04T00:00:00Z"

    def meta(contract_type: str, contract_id: str, *, created_by: str = "role.architect") -> dict:
        return {
            "type": contract_type,
            "id": contract_id,
            "version": "1.0.0",
            "status": "active",
            "created_by": created_by,
            "created_at": now,
            "dependencies": [],
            "validation": {"schema": f"contracts/schemas/{contract_type}.contract.schema.json", "checks": []},
            "on_failure": {"action": "retry", "max_retries": 2, "severity": "mid"},
        }

    contracts_dir = project_root / "contracts" / "instances" / "user_auth"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    behavior = {
        "contract": {
            "meta": meta("behavior", "behavior.user_auth", created_by="role.qa"),
            "spec": {
                "test_suite": {
                    "runner": "pytest",
                    "entry": "tests/backend/test_user_auth.py",
                    "command": "pytest -q tests/backend/test_user_auth.py",
                },
                "mandatory_cases": [{"id": "TC001", "description": "works", "must_pass": True}],
            },
            "extensions": {},
        }
    }
    interface = {
        "contract": {
            "meta": meta("interface", "interface.user_auth"),
            "spec": {
                "endpoints": [
                    {
                        "id": "login",
                        "path": "/api/auth/login",
                        "method": "POST",
                        "request": {"schema": {"type": "object"}},
                        "response": {"success": {"status": 200, "schema": {"type": "object"}}},
                    }
                ],
                "binding": {"producer": "role.coder_backend", "consumers": []},
                "change_policy": {"requires_approval": ["role.architect"], "on_change": "suspend_dependent_tasks"},
            },
            "extensions": {},
        }
    }
    task = {
        "contract": {
            "meta": meta("task", "task.user_auth.login_api"),
            "spec": {
                "assigned_to": "role.coder_backend",
                "scope": {"include": ["src/backend/**"], "exclude": [], "create_allowed": ["src/backend/"]},
                "acceptance": {
                    "behavior_ref": {"id": "behavior.user_auth", "version": "1.0.0"},
                    "interface_refs": [{"id": "interface.user_auth", "version": "1.0.0"}],
                    "max_new_files": 5,
                },
                "token_budget": 8000,
            },
            "extensions": {},
        }
    }

    (contracts_dir / "behavior.contract.yaml").write_text(yaml.safe_dump(behavior, sort_keys=False), encoding="utf-8")
    (contracts_dir / "interface.contract.yaml").write_text(yaml.safe_dump(interface, sort_keys=False), encoding="utf-8")
    (contracts_dir / "task.contract.yaml").write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")

    issues = validate_project(project_root)
    errors = [issue for issue in issues if issue.level == "error"]
    assert errors == []

    registry = Registry.build(project_root)
    assert registry.load_errors == ()

    validator = Validator(registry, sm)
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_executor.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=["src/backend/auth.py"],
        commands_ran=[CommandRecord(cmd="codex exec task", exit_code=0, duration_ms=20)],
        agent_output="ok",
        duration_ms=20,
    )
    mock_runner = MagicMock()
    mock_runner.run.return_value = TestResult(
        passed=True,
        exit_code=0,
        command="pytest -q tests/backend/test_user_auth.py",
        stdout="ok",
        stderr="",
        duration_ms=30,
        summary="All tests passed",
        error_details=[],
    )

    orchestrator = Orchestrator(
        registry=registry,
        state_manager=sm,
        validator=validator,
        executor=mock_executor,
        test_runner=mock_runner,
        project_root=project_root,
    )
    workflow = WorkflowDef(
        id="workflow.integration.scaffold",
        nodes=[WorkflowNode(id="coder_backend", role="role.coder_backend", action="implement", human_review=False)],
    )
    result = orchestrator.run(workflow, ContractRef(id="task.user_auth.login_api", version="1.0.0"))
    assert result.status in {"completed", "waiting_human", "halted"}

    state = sm.load()
    assert state.project_id == "test-project"
    assert len(state.run_history) > 0
