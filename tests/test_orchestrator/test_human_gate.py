from __future__ import annotations

from unittest.mock import MagicMock

from core.executor.port import ExecutorPort
from core.models.workflow import WorkflowDef, WorkflowNode
from core.test_runner import TestResult, TestRunner


def _workflow(human_review: bool) -> WorkflowDef:
    return WorkflowDef(
        id="workflow.human_gate",
        nodes=[
            WorkflowNode(
                id="coder_backend",
                role="role.coder_backend",
                action="implement",
                human_review=human_review,
            )
        ],
    )


def test_human_review_node_waits_for_human(build_orchestrator) -> None:
    env = build_orchestrator(task_max_retries=1)

    result = env["orchestrator"].run(_workflow(human_review=True), env["task_ref"])

    assert result.status == "waiting_human"
    assert result.current_node_id == "coder_backend"


def test_l3_halt_moves_state_to_waiting_human(build_orchestrator) -> None:
    mock_executor = MagicMock(spec=ExecutorPort)
    mock_runner = MagicMock(spec=TestRunner)
    mock_runner.run.return_value = TestResult(
        passed=True,
        exit_code=0,
        command="pytest -q tests/backend/test_user_auth.py",
        stdout="ok",
        stderr="",
        duration_ms=100,
        summary="All tests passed",
        error_details=[],
    )

    env = build_orchestrator(executor=mock_executor, test_runner=mock_runner)
    mock_executor.execute.return_value = env["execution_result"](
        success=True,
        modified_files=["contracts/schemas/evil.json"],
    )
    result = env["orchestrator"].run(_workflow(human_review=False), env["task_ref"])

    assert result.status == "halted"
    state = env["state_manager"].load()
    assert state.status.value == "waiting_human"
    assert env["state_manager"].pending_human_items(state)
