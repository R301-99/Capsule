from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.models.base import ContractRef
from core.models.evidence import CommandRecord
from core.models.execution import ExecutionRequest, ExecutionResult


@pytest.fixture
def execution_request(tmp_path: Path) -> ExecutionRequest:
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    return ExecutionRequest(
        run_id="20260304-000001-abcd1234",
        role_id="role.coder_backend",
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.0.0"),
        working_dir=str(workdir),
        allowed_write=["src/**"],
        allowed_exec=["pytest", "python"],
        prohibited_write=["state/**"],
        prohibited_exec=["git push"],
        task_prompt="Implement feature X",
        injected_context={"phase": "development"},
        timeout_seconds=300,
    )


@pytest.fixture
def execution_result_success() -> ExecutionResult:
    return ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=["src/backend/auth.py"],
        commands_ran=[CommandRecord(cmd="codex exec --full-auto --json 'x'", exit_code=0, duration_ms=100)],
        agent_output="done",
        error_message=None,
        duration_ms=100,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(["git", "init"], repo)
    _run_git(["git", "config", "user.name", "Capsule Test"], repo)
    _run_git(["git", "config", "user.email", "capsule@example.com"], repo)
    _run_git(["git", "config", "commit.gpgsign", "false"], repo)

    (repo / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _run_git(["git", "add", "-A"], repo)
    _run_git(["git", "commit", "-m", "init"], repo)
    return repo


def _run_git(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(cmd)}\n{completed.stderr}")
