from __future__ import annotations

from core.cli import main
from core.models.base import ContractRef
from core.state_manager import StateManager


def test_decide_records_and_resolves_item(initialized_project) -> None:
    sm = StateManager(initialized_project / "state")
    state = sm.load()
    state, run = sm.create_run(
        state,
        ContractRef(id="task.user_auth.login_api", version="1.0.0"),
        "role.coder_backend",
        "coder_backend",
    )
    state, item = sm.enqueue_human(
        state,
        run.run_id,
        "retry_exceeded",
        "Task failed",
        ["approve", "abort"],
    )
    sm.save(state)

    code = main(
        [
            "decide",
            "--item",
            item.item_id,
            "--option",
            "approve",
            "--rationale",
            "Looks good",
            "--root",
            str(initialized_project),
        ]
    )

    assert code == 0
    state = sm.load()
    assert sm.pending_human_items(state) == []
    hd_dir = sm.run_dir(run.run_id) / "human_decisions"
    assert hd_dir.exists()
    assert any(hd_dir.iterdir())


def test_decide_rejects_invalid_option(initialized_project) -> None:
    sm = StateManager(initialized_project / "state")
    state = sm.load()
    state, item = sm.enqueue_human(
        state,
        "run-001",
        "review_required",
        "Need review",
        ["approve", "abort"],
    )
    sm.save(state)

    code = main(
        [
            "decide",
            "--item",
            item.item_id,
            "--option",
            "invalid_option",
            "--root",
            str(initialized_project),
        ]
    )

    assert code == 1
