from __future__ import annotations

import pytest

from core.models.state import ProjectStatus
from core.models.workflow import WorkflowDef, WorkflowNode


def _single_node_review_workflow() -> WorkflowDef:
    return WorkflowDef(
        id="workflow.resume",
        nodes=[
            WorkflowNode(
                id="coder_backend",
                role="role.coder_backend",
                action="implement",
                human_review=True,
            )
        ],
    )


def test_resume_fails_when_status_invalid(build_orchestrator) -> None:
    env = build_orchestrator()
    state = env["state_manager"].load()
    state.status = ProjectStatus.IDLE
    env["state_manager"].save(state)

    with pytest.raises(ValueError):
        env["orchestrator"].resume(_single_node_review_workflow())


def test_resume_fails_with_unresolved_human_items(build_orchestrator) -> None:
    env = build_orchestrator()
    workflow = _single_node_review_workflow()
    first = env["orchestrator"].run(workflow, env["task_ref"])
    assert first.status == "waiting_human"

    with pytest.raises(ValueError):
        env["orchestrator"].resume(workflow)


def test_resume_continues_from_correct_node(build_orchestrator) -> None:
    env = build_orchestrator()
    workflow = _single_node_review_workflow()

    first = env["orchestrator"].run(workflow, env["task_ref"])
    assert first.status == "waiting_human"

    state = env["state_manager"].load()
    for item in env["state_manager"].pending_human_items(state):
        state = env["state_manager"].resolve_human(state, item.item_id, "HD-test-001")
    env["state_manager"].save(state)

    resumed = env["orchestrator"].resume(workflow)
    assert resumed.status == "completed"
