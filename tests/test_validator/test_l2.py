from __future__ import annotations

import subprocess
from unittest.mock import patch

from core.models.base import ContractRef
from core.models.enums import GateLevel
from core.test_runner import TestResult, TestRunner


def _prepare_run(env: dict):
    registry = env["registry"]
    state_manager = env["state_manager"]
    validator = env["validator"]
    state = env["state"]

    task_contract = registry.resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)
    state, run = state_manager.create_run(state, task_ref, "role.coder_backend", "coder_backend")
    input_result = validator.input_gate(state, task_ref, "role.coder_backend")
    assert input_result.passed is True
    state_manager.lock_refs(state, input_result.resolved_refs)
    env["state"] = state
    return state, run, input_result.resolved_refs


def _valid_evidence(run_id: str, task_ref: ContractRef, snapshot_refs: list[ContractRef]) -> dict:
    command_record = {"cmd": "pytest -q tests/backend/test_auth.py", "exit_code": 0, "duration_ms": 120}
    return {
        "run_id": run_id,
        "role_id": "role.coder_backend",
        "task_ref": {"id": task_ref.id, "version": task_ref.version},
        "contract_snapshot": {"refs": [ref.model_dump(mode="json") for ref in snapshot_refs]},
        "changes": {"modified_files": ["src/backend/auth.py"], "diff_stat": {"files": 1, "insertions": 4, "deletions": 1}},
        "commands": {"ran": [command_record]},
        "tests": {"ran": [command_record], "summary": "pass"},
        "self_report": {"confidence": 0.92, "risks": [], "notes": "done"},
    }


class _RunnerPass:
    def run(self, command, working_dir):
        return TestResult(
            passed=True,
            exit_code=0,
            command=command,
            stdout="12 passed",
            stderr="",
            duration_ms=220,
            summary="All tests passed",
            error_details=[],
        )


class _RunnerFail:
    def run(self, command, working_dir):
        return TestResult(
            passed=False,
            exit_code=1,
            command=command,
            stdout="11 passed, 1 failed",
            stderr="FAILED test_auth.py::test_login",
            duration_ms=300,
            summary="11 passed, 1 failed",
            error_details=["FAILED test_auth.py::test_login"],
        )


@patch("core.test_runner.subprocess.run")
def test_test_runner_pass(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="12 passed",
        stderr="",
    )
    runner = TestRunner(timeout_seconds=30)

    result = runner.run("pytest -q", ".")

    assert result.passed is True
    assert result.summary == "All tests passed"


@patch("core.test_runner.subprocess.run")
def test_test_runner_failure_extracts_error_details(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=1,
        stdout="FAILED tests/test_auth.py::test_login",
        stderr="ERROR details",
    )
    runner = TestRunner(timeout_seconds=30)

    result = runner.run("pytest -q", ".")

    assert result.passed is False
    assert result.error_details
    assert any("FAILED" in item or "ERROR" in item for item in result.error_details)


@patch("core.test_runner.subprocess.run")
def test_test_runner_timeout(mock_run) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest -q", timeout=1, output="x", stderr="timeout")
    runner = TestRunner(timeout_seconds=1)

    result = runner.run("pytest -q", ".")

    assert result.passed is False
    assert "timed out" in result.summary


@patch("core.test_runner.subprocess.run")
def test_test_runner_command_not_found(mock_run) -> None:
    mock_run.side_effect = FileNotFoundError()
    runner = TestRunner()

    result = runner.run("missing-cmd", ".")

    assert result.passed is False
    assert "not found" in result.summary


@patch("core.test_runner.subprocess.run")
def test_test_runner_truncates_output(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="x" * 7000,
        stderr="y" * 7000,
    )
    runner = TestRunner()

    result = runner.run("pytest -q", ".")

    assert len(result.stdout) <= 5000 + len("\n... [truncated]")
    assert len(result.stderr) <= 5000 + len("\n... [truncated]")
    assert result.stdout.endswith("... [truncated]")
    assert result.stderr.endswith("... [truncated]")


def test_output_gate_l2_passes_with_test_runner(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
        test_runner=_RunnerPass(),
        working_dir=str(env["project_root"]),
    )

    assert result.passed is True
    assert result.halt is False
    assert result.l2_result is not None
    assert result.l2_result["status"] == "passed"


def test_output_gate_l2_failure_produces_rejection_when_l3_passes(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
        test_runner=_RunnerFail(),
        working_dir=str(env["project_root"]),
    )

    assert result.passed is False
    assert result.halt is False
    assert result.rejection is not None
    assert result.rejection.failed_level == GateLevel.L2
    assert result.l2_result is not None
    assert result.l2_result["status"] == "failed"


def test_output_gate_l2_failure_and_l3_violation_halts(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["contracts/schemas/foo.json"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
        test_runner=_RunnerFail(),
        working_dir=str(env["project_root"]),
    )

    assert result.passed is False
    assert result.halt is True
    assert result.rejection is None
    assert result.l2_result is not None
    assert result.l2_result["status"] == "failed"


def test_output_gate_l2_skipped_when_runner_not_provided(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.l2_result is not None
    assert result.l2_result["status"] == "skipped"


def test_output_gate_l2_fails_when_behavior_contract_unavailable(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)
    _ = locked_refs

    validator = env["validator"]
    validator._resolve_behavior_ref_for_l2 = lambda **kwargs: ContractRef(  # type: ignore[attr-defined]
        id="behavior.missing",
        version="1.0.0",
    )

    result = validator.output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, state.locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
        test_runner=_RunnerPass(),
        working_dir=str(env["project_root"]),
    )

    assert result.passed is False
    assert result.halt is False
    assert result.rejection is not None
    assert result.rejection.failed_level == GateLevel.L2
    assert result.l2_result is not None
    assert result.l2_result["status"] == "failed"

