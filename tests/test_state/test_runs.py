from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.models.base import ContractRef
from core.models.state import ProjectStatus, RunStatus
from core.state_manager import RunNotFoundError, StateManager


def _create_run(manager: StateManager):
    state = manager.init_project("test-proj")
    task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
    state, run = manager.create_run(
        state=state,
        task_ref=task_ref,
        role_id="role.coder_backend",
        node_id="coder_backend",
    )
    return state, run


def test_create_run_creates_record_and_directories(manager: StateManager) -> None:
    state, run = _create_run(manager)

    assert len(state.run_history) == 1
    assert state.run_history[0].run_id == run.run_id
    assert re.match(r"^\d{8}-\d{6}-[0-9a-f]{8}$", run.run_id)
    assert run.status == RunStatus.PENDING
    assert state.status == ProjectStatus.RUNNING
    assert state.current_task_ref is not None
    assert (manager.run_dir(run.run_id) / "gate_reports").is_dir()
    assert (manager.run_dir(run.run_id) / "rejections").is_dir()
    assert (manager.run_dir(run.run_id) / "human_decisions").is_dir()


def test_create_run_requires_exact_task_version(manager: StateManager) -> None:
    state = manager.init_project("test-proj")

    with pytest.raises(ValueError):
        manager.create_run(
            state=state,
            task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
            role_id="role.coder_backend",
            node_id="coder_backend",
        )


def test_update_run_status_updates_fields(manager: StateManager) -> None:
    state, run = _create_run(manager)

    manager.update_run_status(
        state=state,
        run_id=run.run_id,
        new_status=RunStatus.PASSED,
        finished_at="2026-03-04T00:00:00Z",
        evidence_path=f"state/runs/{run.run_id}/evidence.json",
        input_gate_path=f"state/runs/{run.run_id}/gate_reports/input.json",
        output_gate_path=f"state/runs/{run.run_id}/gate_reports/output.json",
    )

    updated = manager.get_run(state, run.run_id)
    assert updated is not None
    assert updated.status == RunStatus.PASSED
    assert updated.finished_at == "2026-03-04T00:00:00Z"
    assert updated.evidence_path is not None
    assert updated.input_gate_path is not None
    assert updated.output_gate_path is not None


def test_update_run_status_raises_when_run_missing(manager: StateManager) -> None:
    state = manager.init_project("test-proj")

    with pytest.raises(RunNotFoundError):
        manager.update_run_status(state=state, run_id="missing-run", new_status=RunStatus.EXECUTING)


def test_increment_retry_increases_retry_count(manager: StateManager) -> None:
    state, run = _create_run(manager)

    manager.increment_retry(state=state, run_id=run.run_id)
    manager.increment_retry(state=state, run_id=run.run_id)

    updated = manager.get_run(state, run.run_id)
    assert updated is not None
    assert updated.retry_count == 2


def test_current_run_returns_last_active_run(manager: StateManager) -> None:
    state, run1 = _create_run(manager)
    manager.update_run_status(state, run1.run_id, RunStatus.PASSED)

    task_ref = ContractRef(id="task.user_auth.profile_api", version="1.0.0")
    state, run2 = manager.create_run(state, task_ref, "role.coder_backend", "coder_backend")

    current = manager.current_run(state)
    assert current is not None
    assert current.run_id == run2.run_id


def test_current_run_returns_none_when_all_terminal(manager: StateManager) -> None:
    state, run = _create_run(manager)
    manager.update_run_status(state, run.run_id, RunStatus.HALTED)

    assert manager.current_run(state) is None


def test_get_run_returns_run_or_none(manager: StateManager) -> None:
    state, run = _create_run(manager)

    assert manager.get_run(state, run.run_id) is not None
    assert manager.get_run(state, "missing-run") is None


def test_write_gate_report_writes_expected_path(manager: StateManager) -> None:
    _, run = _create_run(manager)

    path = manager.write_gate_report(run.run_id, "INPUT_GATE", {"result": "pass"})

    assert path.name == "input.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["result"] == "pass"


def test_write_gate_report_raises_for_missing_run(manager: StateManager) -> None:
    manager.init_project("test-proj")

    with pytest.raises(RunNotFoundError):
        manager.write_gate_report("missing-run", "INPUT_GATE", {"result": "pass"})


def test_write_evidence_writes_expected_path(manager: StateManager) -> None:
    _, run = _create_run(manager)

    path = manager.write_evidence(run.run_id, {"run_id": run.run_id, "confidence": 0.9})

    assert path.name == "evidence.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run.run_id


def test_write_rejection_uses_rejection_id_or_sequence(manager: StateManager) -> None:
    _, run = _create_run(manager)

    named = manager.write_rejection(run.run_id, {"rejection_id": "rej-001", "summary": "blocked"})
    seq = manager.write_rejection(run.run_id, {"summary": "retry"})

    assert named.name == "rej-001.json"
    assert seq.exists()
    assert seq.parent.name == "rejections"


def test_write_human_decision_uses_decision_id_or_sequence(manager: StateManager) -> None:
    _, run = _create_run(manager)

    named = manager.write_human_decision(run.run_id, {"decision_id": "dec-001", "action": "resume"})
    seq = manager.write_human_decision(run.run_id, {"action": "pause"})

    assert named.name == "dec-001.json"
    assert seq.exists()
    assert seq.parent.name == "human_decisions"


def test_append_boundary_violation_appends_lines(manager: StateManager, state_dir: Path) -> None:
    manager.init_project("test-proj")
    manager.append_boundary_violation("first issue")
    manager.append_boundary_violation("second issue")

    log_path = state_dir / "audit" / "boundary_violations.log"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert "first issue" in lines[0]
    assert "second issue" in lines[1]


def test_lock_and_clear_locked_refs(manager: StateManager) -> None:
    state = manager.init_project("test-proj")
    refs = [
        ContractRef(id="behavior.user_auth", version="1.2.3"),
        ContractRef(id="interface.user_auth", version="1.0.0"),
    ]

    manager.lock_refs(state, refs)
    assert [(item.id, item.version) for item in state.locked_refs] == [
        ("behavior.user_auth", "1.2.3"),
        ("interface.user_auth", "1.0.0"),
    ]

    manager.clear_locked_refs(state)
    assert state.locked_refs == []
