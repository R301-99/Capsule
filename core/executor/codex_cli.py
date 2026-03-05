from __future__ import annotations

import shlex
import subprocess
import time

from core.models.evidence import CommandRecord
from core.models.execution import ExecutionRequest, ExecutionResult

from . import git_utils
from .port import ExecutorPort

_OUTPUT_LIMIT = 10000
_TRUNCATED_SUFFIX = "\n... [truncated]"


class CodexCliExecutor(ExecutorPort):
    def __init__(self, codex_command: str = "codex", default_timeout: int = 300) -> None:
        self._codex_command = codex_command
        self._default_timeout = default_timeout

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        start = time.monotonic()
        pre_files = set(git_utils.get_modified_files(request.working_dir))
        command = [
            self._codex_command,
            "exec",
            "--full-auto",
            "--json",
            request.task_prompt,
        ]
        command_str = shlex.join(command)
        timeout = request.timeout_seconds or self._default_timeout
        exit_code: int | None = None
        error_message: str | None = None
        stdout_text = ""
        stderr_text = ""

        try:
            completed = subprocess.run(
                command,
                cwd=request.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            exit_code = completed.returncode
            stdout_text = completed.stdout or ""
            stderr_text = completed.stderr or ""
        except subprocess.TimeoutExpired:
            error_message = f"Execution timed out after {timeout}s"
        except FileNotFoundError:
            error_message = f"codex command not found: {self._codex_command}"
        except Exception as exc:  # pragma: no cover - defensive
            error_message = str(exc)

        post_files = set(git_utils.get_modified_files(request.working_dir))
        modified_files = sorted(post_files - pre_files)
        duration_ms = int((time.monotonic() - start) * 1000)
        success = error_message is None and exit_code == 0
        command_exit = exit_code if exit_code is not None else -1
        output_source = stdout_text if stdout_text else stderr_text
        agent_output = _truncate_output(output_source)

        return ExecutionResult(
            success=success,
            exit_code=exit_code,
            modified_files=modified_files,
            commands_ran=[
                CommandRecord(
                    cmd=command_str,
                    exit_code=command_exit,
                    duration_ms=duration_ms,
                )
            ],
            agent_output=agent_output,
            error_message=error_message,
            duration_ms=duration_ms,
        )


def _truncate_output(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    return text[:_OUTPUT_LIMIT] + _TRUNCATED_SUFFIX

