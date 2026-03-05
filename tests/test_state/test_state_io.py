from __future__ import annotations

from pathlib import Path

import pytest

from core.state_manager import StateLoadError, StateManager


def test_init_project_creates_state_file_and_directories(manager: StateManager, state_dir: Path) -> None:
    state = manager.init_project("test-proj")

    assert state.project_id == "test-proj"
    assert (state_dir / "PROJECT_STATE.json").exists()
    assert (state_dir / "runs").is_dir()
    assert (state_dir / "checkpoints").is_dir()
    assert (state_dir / "audit").is_dir()
    assert (state_dir / "audit" / "boundary_violations.log").exists()


def test_load_returns_project_state(manager: StateManager) -> None:
    created = manager.init_project("test-proj")

    loaded = manager.load()

    assert loaded.project_id == created.project_id
    assert loaded.status == created.status
    assert loaded.created_at == created.created_at


def test_save_updates_updated_at_and_roundtrip(manager: StateManager) -> None:
    state = manager.init_project("test-proj")
    state.phase = "development"
    state.global_conventions["lang"] = "python"
    state.updated_at = "2000-01-01T00:00:00Z"
    old_updated = state.updated_at

    manager.save(state)
    loaded = manager.load()

    assert loaded.updated_at != old_updated
    assert loaded.model_dump(mode="json") == state.model_dump(mode="json")


def test_init_project_raises_when_state_already_exists(manager: StateManager) -> None:
    manager.init_project("test-proj")

    with pytest.raises(FileExistsError):
        manager.init_project("test-proj")


def test_load_raises_when_project_state_missing(manager: StateManager) -> None:
    with pytest.raises(StateLoadError):
        manager.load()


def test_load_raises_when_project_state_is_invalid(manager: StateManager, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "PROJECT_STATE.json").write_text("{invalid json", encoding="utf-8")

    with pytest.raises(StateLoadError):
        manager.load()


def test_save_does_not_leave_tmp_file(manager: StateManager, state_dir: Path) -> None:
    state = manager.init_project("test-proj")

    manager.save(state)

    assert not (state_dir / "PROJECT_STATE.json.tmp").exists()

