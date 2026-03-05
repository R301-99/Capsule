from __future__ import annotations

import re

import pytest

from core.models.base import ContractRef
from core.models.enums import HumanTrigger
from core.models.state import ProjectStatus
from core.state_manager import HumanQueueItemNotFoundError, StateManager


def _create_running_state(manager: StateManager):
    state = manager.init_project("test-proj")
    state, run = manager.create_run(
        state=state,
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.0.0"),
        role_id="role.coder_backend",
        node_id="coder_backend",
    )
    return state, run


def test_enqueue_human_adds_item_and_sets_waiting_status(manager: StateManager) -> None:
    state, run = _create_running_state(manager)

    state, item = manager.enqueue_human(
        state=state,
        run_id=run.run_id,
        trigger=HumanTrigger.REVIEW_REQUIRED,
        summary="Need review from human",
        options=["resume", "abort"],
    )

    assert len(state.human_queue) == 1
    assert item.run_id == run.run_id
    assert re.match(r"^hq-\d{8}-\d{6}-[0-9a-f]{8}$", item.item_id)
    assert state.status == ProjectStatus.WAITING_HUMAN


def test_enqueue_human_allows_missing_run_id(manager: StateManager) -> None:
    state = manager.init_project("test-proj")

    state, item = manager.enqueue_human(
        state=state,
        run_id="missing-run",
        trigger=HumanTrigger.REVIEW_REQUIRED,
        summary="Need review",
        options=["resume"],
    )

    assert item.run_id == "missing-run"
    assert state.status == ProjectStatus.WAITING_HUMAN


def test_pending_human_items_returns_only_unresolved(manager: StateManager) -> None:
    state, run = _create_running_state(manager)
    state, item1 = manager.enqueue_human(
        state=state,
        run_id=run.run_id,
        trigger=HumanTrigger.RETRY_EXCEEDED,
        summary="first",
        options=["resume"],
    )
    state, item2 = manager.enqueue_human(
        state=state,
        run_id=run.run_id,
        trigger=HumanTrigger.REVIEW_REQUIRED,
        summary="second",
        options=["abort"],
    )
    manager.resolve_human(state, item1.item_id, "decision-1")

    pending = manager.pending_human_items(state)
    assert [item.item_id for item in pending] == [item2.item_id]


def test_resolve_human_marks_item_and_sets_decision_id(manager: StateManager) -> None:
    state, run = _create_running_state(manager)
    state, item = manager.enqueue_human(
        state=state,
        run_id=run.run_id,
        trigger=HumanTrigger.REVIEW_REQUIRED,
        summary="review needed",
        options=["resume", "abort"],
    )

    manager.resolve_human(state, item.item_id, "decision-001")

    resolved = state.human_queue[0]
    assert resolved.resolved is True
    assert resolved.decision_id == "decision-001"


def test_resolve_human_restores_running_when_no_pending(manager: StateManager) -> None:
    state, run = _create_running_state(manager)
    state, item = manager.enqueue_human(
        state=state,
        run_id=run.run_id,
        trigger=HumanTrigger.REVIEW_REQUIRED,
        summary="review needed",
        options=["resume"],
    )

    manager.resolve_human(state, item.item_id, "decision-001")

    assert manager.pending_human_items(state) == []
    assert state.status == ProjectStatus.RUNNING


def test_resolve_human_raises_when_item_missing(manager: StateManager) -> None:
    state, _ = _create_running_state(manager)

    with pytest.raises(HumanQueueItemNotFoundError):
        manager.resolve_human(state, "missing-item", "decision-001")
