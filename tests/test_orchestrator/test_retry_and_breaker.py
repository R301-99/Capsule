from __future__ import annotations

from unittest.mock import MagicMock

from core.executor.port import ExecutorPort
from core.models.state import RunStatus
from core.models.workflow import WorkflowDef, WorkflowNode
from core.test_runner import TestResult, TestRunner


def _single_node_workflow() -> WorkflowDef:
    return WorkflowDef(
        id="workflow.retry",
        nodes=[WorkflowNode(id="coder_backend", role="role.coder_backend", action="implement")],
    )


def test_retry_once_then_pass_sets_retry_count(build_orchestrator) -> None:
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_runner = MagicMock(spec=TestRunner)
    mock_runner.run.side_effect = [
        TestResult(
            passed=False,
            exit_code=1,
            command="pytest -q tests/backend/test_user_auth.py",
            stdout="1 failed",
            stderr="FAILED test_x",
            duration_ms=100,
            summary="1 failed",
            error_details=["FAILED test_x"],
        ),
        TestResult(
            passed=True,
            exit_code=0,
            command="pytest -q tests/backend/test_user_auth.py",
            stdout="ok",
            stderr="",
            duration_ms=100,
            summary="All tests passed",
            error_details=[],
        ),
    ]

    env = build_orchestrator(task_max_retries=2, executor=mock_executor, test_runner=mock_runner)
    mock_executor.execute.return_value = env["execution_result"](success=True)
    result = env["orchestrator"].run(_single_node_workflow(), env["task_ref"])

    assert result.status == "completed"
    assert mock_executor.execute.call_count == 2
    state = env["state_manager"].load()
    assert state.run_history[-1].retry_count == 1
    assert state.run_history[-1].status == RunStatus.PASSED


def test_retry_exhausted_triggers_human_queue(build_orchestrator) -> None:
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_runner = MagicMock(spec=TestRunner)
    mock_runner.run.return_value = TestResult(
        passed=False,
        exit_code=1,
        command="pytest -q tests/backend/test_user_auth.py",
        stdout="failed",
        stderr="FAILED",
        duration_ms=100,
        summary="failed",
        error_details=["FAILED"],
    )

    env = build_orchestrator(task_max_retries=1, executor=mock_executor, test_runner=mock_runner)
    mock_executor.execute.return_value = env["execution_result"](success=True)
    result = env["orchestrator"].run(_single_node_workflow(), env["task_ref"])

    assert result.status == "waiting_human"
    assert result.human_items
    assert any(item.trigger.value == "retry_exceeded" for item in result.human_items)


def test_max_retries_priority_task_over_role_then_default(build_orchestrator) -> None:
    env = build_orchestrator(task_max_retries=2, role_retry_max=9)
    task_contract = env["registry"].resolve(env["task_ref"])
    role_contract = env["registry"].get_latest_active("role.coder_backend")

    assert env["orchestrator"]._resolve_max_retries(task_contract, role_contract) == 2
    assert env["orchestrator"]._resolve_max_retries(None, role_contract) == 9
    assert env["orchestrator"]._resolve_max_retries(None, None) == 3
