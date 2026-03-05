from __future__ import annotations

import subprocess
from unittest.mock import patch

from core.executor.codex_cli import CodexCliExecutor
from core.models.execution import ExecutionRequest


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["codex"], returncode=returncode, stdout=stdout, stderr=stderr)


@patch("core.executor.codex_cli.git_utils.get_modified_files")
@patch("core.executor.codex_cli.subprocess.run")
def test_codex_cli_success(mock_run, mock_get_modified, execution_request: ExecutionRequest) -> None:
    mock_get_modified.side_effect = [[], ["src/foo.py"]]
    mock_run.return_value = _completed(0, stdout="some output")
    executor = CodexCliExecutor()

    result = executor.execute(execution_request)

    assert result.success is True
    assert result.exit_code == 0
    assert result.modified_files == ["src/foo.py"]
    assert "some output" in result.agent_output
    assert result.error_message is None


@patch("core.executor.codex_cli.git_utils.get_modified_files")
@patch("core.executor.codex_cli.subprocess.run")
def test_codex_cli_non_zero_exit(mock_run, mock_get_modified, execution_request: ExecutionRequest) -> None:
    mock_get_modified.side_effect = [[], []]
    mock_run.return_value = _completed(1, stdout="failed")
    executor = CodexCliExecutor()

    result = executor.execute(execution_request)

    assert result.success is False
    assert result.exit_code == 1
    assert result.error_message is None


@patch("core.executor.codex_cli.git_utils.get_modified_files")
@patch("core.executor.codex_cli.subprocess.run")
def test_codex_cli_timeout(mock_run, mock_get_modified, execution_request: ExecutionRequest) -> None:
    mock_get_modified.side_effect = [[], []]
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=300)
    executor = CodexCliExecutor()

    result = executor.execute(execution_request)

    assert result.success is False
    assert result.exit_code is None
    assert result.error_message is not None
    assert "timed out" in result.error_message


@patch("core.executor.codex_cli.git_utils.get_modified_files")
@patch("core.executor.codex_cli.subprocess.run")
def test_codex_cli_command_not_found(mock_run, mock_get_modified, execution_request: ExecutionRequest) -> None:
    mock_get_modified.side_effect = [[], []]
    mock_run.side_effect = FileNotFoundError()
    executor = CodexCliExecutor(codex_command="codex-missing")

    result = executor.execute(execution_request)

    assert result.success is False
    assert result.error_message is not None
    assert "not found" in result.error_message


@patch("core.executor.codex_cli.git_utils.get_modified_files")
@patch("core.executor.codex_cli.subprocess.run")
def test_codex_cli_truncates_output(mock_run, mock_get_modified, execution_request: ExecutionRequest) -> None:
    mock_get_modified.side_effect = [[], []]
    mock_run.return_value = _completed(0, stdout="x" * 20000)
    executor = CodexCliExecutor()

    result = executor.execute(execution_request)

    assert len(result.agent_output) <= 10000 + len("\n... [truncated]")
    assert result.agent_output.endswith("... [truncated]")


@patch("core.executor.codex_cli.git_utils.get_modified_files")
@patch("core.executor.codex_cli.subprocess.run")
def test_codex_cli_modified_files_diff_uses_post_minus_pre(mock_run, mock_get_modified, execution_request: ExecutionRequest) -> None:
    mock_get_modified.side_effect = [["dirty.txt"], ["dirty.txt", "new.py"]]
    mock_run.return_value = _completed(0, stdout="ok")
    executor = CodexCliExecutor()

    result = executor.execute(execution_request)

    assert result.modified_files == ["new.py"]

