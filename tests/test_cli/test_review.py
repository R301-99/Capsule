from __future__ import annotations

from core.cli import main
from core.state_manager import StateManager


def test_review_lists_pending_items(initialized_project, capsys) -> None:
    sm = StateManager(initialized_project / "state")
    state = sm.load()
    state, _ = sm.enqueue_human(
        state,
        "run-001",
        "review_required",
        "Need your review",
        ["approve", "abort"],
    )
    sm.save(state)

    code = main(["review", "--root", str(initialized_project)])

    out = capsys.readouterr().out
    assert code == 0
    assert "HUMAN REVIEW REQUIRED" in out
    assert "approve" in out


def test_review_no_pending_prints_message(initialized_project, capsys) -> None:
    code = main(["review", "--root", str(initialized_project)])

    out = capsys.readouterr().out
    assert code == 0
    assert "No pending reviews." in out
