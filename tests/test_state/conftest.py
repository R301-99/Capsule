from __future__ import annotations

from pathlib import Path

import pytest

from core.state_manager import StateManager


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def manager(state_dir: Path) -> StateManager:
    return StateManager(state_dir=state_dir)

