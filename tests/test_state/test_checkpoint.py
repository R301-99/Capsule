from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.models.base import ContractRef
from core.state_manager import CheckpointNotFoundError, StateManager


def test_save_checkpoint_creates_file_and_updates_active_id(manager: StateManager, state_dir: Path) -> None:
    state = manager.init_project("test-proj")
    checkpoint_id = manager.save_checkpoint(state)

    assert re.match(r"^ckpt-\d{8}-\d{6}-[0-9a-f]{8}$", checkpoint_id)
    assert state.active_checkpoint_id == checkpoint_id
    assert (state_dir / "checkpoints" / f"{checkpoint_id}.json").exists()


def test_load_checkpoint_returns_saved_state(manager: StateManager) -> None:
    state = manager.init_project("test-proj")
    state.phase = "development"
    state.current_task_ref = ContractRef(id="task.user_auth.login_api", version="1.0.0")
    expected = state.model_copy(deep=True)
    checkpoint_id = manager.save_checkpoint(state)

    loaded = manager.load_checkpoint(checkpoint_id)

    assert loaded.model_dump(mode="json") == expected.model_dump(mode="json")


def test_load_checkpoint_raises_when_missing(manager: StateManager) -> None:
    manager.init_project("test-proj")

    with pytest.raises(CheckpointNotFoundError):
        manager.load_checkpoint("ckpt-missing")


def test_list_checkpoints_returns_all_ids_sorted(manager: StateManager) -> None:
    state = manager.init_project("test-proj")
    first = manager.save_checkpoint(state)
    state.phase = "review"
    second = manager.save_checkpoint(state)

    checkpoint_ids = manager.list_checkpoints()
    assert checkpoint_ids == sorted([first, second])


def test_old_checkpoint_stays_intact_after_new_changes(manager: StateManager) -> None:
    state = manager.init_project("test-proj")
    state.phase = "development"
    first = manager.save_checkpoint(state)

    state.phase = "review"
    second = manager.save_checkpoint(state)

    first_loaded = manager.load_checkpoint(first)
    second_loaded = manager.load_checkpoint(second)
    assert first_loaded.phase == "development"
    assert second_loaded.phase == "review"
