from __future__ import annotations

from unittest.mock import MagicMock

from core.executor.port import ExecutorPort
from core.models.state import RunStatus
from core.models.workflow import WorkflowDef, WorkflowNode
from core.test_runner import TestResult, TestRunner


def _single_node_workflow(human_review: bool = False) -> WorkflowDef:
    return WorkflowDef(
        id="workflow.single_node",
        nodes=[
            WorkflowNode(
                id="coder_backend",
                role="role.coder_backend",
                action="implement",
                human_review=human_review,
            )
        ],
    )


def test_executor_success_and_gate_pass_marks_run_passed(build_orchestrator) -> None:
    env = build_orchestrator(task_max_retries=1)

    result = env["orchestrator"].run(_single_node_workflow(), env["task_ref"])

    assert result.status == "completed"
    state = env["state_manager"].load()
    assert state.run_history
    assert state.run_history[-1].status == RunStatus.PASSED


def test_executor_failure_still_writes_evidence(build_orchestrator) -> None:
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
    mock_executor.execute.return_value = env["execution_result"](success=False)
    result = env["orchestrator"].run(_single_node_workflow(), env["task_ref"])

    assert result.status in {"completed", "waiting_human", "halted"}
    state = env["state_manager"].load()
    run = state.run_history[-1]
    evidence_path = env["state_manager"].run_dir(run.run_id) / "evidence.json"
    assert evidence_path.exists()


def test_gate_reports_are_written_for_single_node_run(build_orchestrator) -> None:
    env = build_orchestrator(task_max_retries=1)

    result = env["orchestrator"].run(_single_node_workflow(), env["task_ref"])

    assert result.status in {"completed", "waiting_human", "halted"}
    state = env["state_manager"].load()
    run = state.run_history[-1]
    run_root = env["state_manager"].run_dir(run.run_id)
    assert (run_root / "gate_reports" / "input.json").exists()
    assert (run_root / "gate_reports" / "output.json").exists()
