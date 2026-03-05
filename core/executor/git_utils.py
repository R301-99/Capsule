from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_modified_files(repo_dir: str | Path) -> list[str]:
    repo = Path(repo_dir)
    tracked = _run_git_capture(repo, ["git", "diff", "--name-only", "HEAD"])
    untracked = _run_git_capture(repo, ["git", "ls-files", "--others", "--exclude-standard"])
    if tracked is None or untracked is None:
        return []
    files = {line.strip() for line in tracked + untracked if line.strip()}
    return sorted(files)


def create_snapshot(repo_dir: str | Path) -> str | None:
    repo = Path(repo_dir)
    lines = _run_git_capture(repo, ["git", "stash", "create"])
    if lines is None:
        return None
    if not lines:
        return None
    snapshot = lines[0].strip()
    return snapshot or None


def stage_all(repo_dir: str | Path) -> bool:
    repo = Path(repo_dir)
    try:
        completed = subprocess.run(
            ["git", "add", "-A"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("git add failed at %s: %s", repo, exc)
        return False
    if completed.returncode != 0:
        logger.warning("git add failed at %s: %s", repo, completed.stderr.strip())
        return False
    return True


def _run_git_capture(repo: Path, cmd: list[str]) -> list[str] | None:
    try:
        completed = subprocess.run(
            cmd,
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("git command failed at %s for %s: %s", repo, " ".join(cmd), exc)
        return None
    if completed.returncode != 0:
        logger.warning("git command failed at %s for %s: %s", repo, " ".join(cmd), completed.stderr.strip())
        return None
    if not completed.stdout:
        return []
    return completed.stdout.splitlines()

