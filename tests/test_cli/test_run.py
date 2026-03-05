from __future__ import annotations

from core.cli import main
from core.models.execution import ExecutionResult
from core.state_manager import StateManager
from core.test_runner import TestResult


def test_run_completes_single_node(initialized_project, patch_cli_runtime) -> None:
    patch_cli_runtime()

    code = main(["run", "--task", "task.user_auth.login_api@1.0.0", "--root", str(initialized_project)])

    assert code == 0
    state = StateManager(initialized_project / "state").load()
    assert state.status.value == "completed"


def test_run_waiting_human_when_retries_exhausted(initialized_project, patch_cli_runtime) -> None:
    patch_cli_runtime(
        exec_results=[
            ExecutionResult(
                success=True,
                exit_code=0,
                modified_files=["src/backend/auth/login.py"],
                commands_ran=[{"cmd": "codex exec task", "exit_code": 0, "duration_ms": 30}],
                agent_output="ok",
                duration_ms=30,
            )
        ],
        test_results=[
            TestResult(
                passed=False,
                exit_code=1,
                command="pytest -q tests/backend/test_user_auth.py",
                stdout="1 failed",
                stderr="FAILED test_user_auth",
                duration_ms=10,
                summary="1 failed",
                error_details=["FAILED test_user_auth"],
            ),
            TestResult(
                passed=False,
                exit_code=1,
                command="pytest -q tests/backend/test_user_auth.py",
                stdout="1 failed",
                stderr="FAILED test_user_auth",
                duration_ms=10,
                summary="1 failed",
                error_details=["FAILED test_user_auth"],
            ),
            TestResult(
                passed=False,
                exit_code=1,
                command="pytest -q tests/backend/test_user_auth.py",
                stdout="1 failed",
                stderr="FAILED test_user_auth",
                duration_ms=10,
                summary="1 failed",
                error_details=["FAILED test_user_auth"],
            ),
        ],
    )

    code = main(["run", "--task", "task.user_auth.login_api@1.0.0", "--root", str(initialized_project)])

    assert code == 0
    state = StateManager(initialized_project / "state").load()
    assert state.status.value == "waiting_human"
    assert len(state.human_queue) > 0
