from __future__ import annotations

import subprocess
from pathlib import Path

from core.executor.git_utils import create_snapshot, get_modified_files, stage_all


def test_get_modified_files_includes_tracked_changes(git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("v2\n", encoding="utf-8")

    files = get_modified_files(git_repo)

    assert "tracked.txt" in files


def test_get_modified_files_includes_untracked_files(git_repo: Path) -> None:
    (git_repo / "new_file.txt").write_text("new\n", encoding="utf-8")

    files = get_modified_files(git_repo)

    assert "new_file.txt" in files


def test_get_modified_files_returns_empty_when_clean(git_repo: Path) -> None:
    files = get_modified_files(git_repo)

    assert files == []


def test_get_modified_files_returns_empty_for_non_git_dir(tmp_path: Path) -> None:
    not_repo = tmp_path / "not_repo"
    not_repo.mkdir(parents=True, exist_ok=True)

    files = get_modified_files(not_repo)

    assert files == []


def test_create_snapshot_returns_hash_when_dirty(git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("v2\n", encoding="utf-8")

    snapshot = create_snapshot(git_repo)

    assert snapshot is not None
    assert len(snapshot) > 0


def test_create_snapshot_returns_none_when_clean(git_repo: Path) -> None:
    snapshot = create_snapshot(git_repo)

    assert snapshot is None


def test_stage_all_returns_true_and_stages_files(git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
    (git_repo / "new_file.txt").write_text("new\n", encoding="utf-8")

    success = stage_all(git_repo)
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert success is True
    assert status.returncode == 0
    assert status.stdout.strip()
    assert " M " not in status.stdout
    assert "?? " not in status.stdout

