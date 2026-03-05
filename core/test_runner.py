from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union

_OUTPUT_LIMIT = 5000
_TRUNCATED_SUFFIX = "\n... [truncated]"


@dataclass(frozen=True)
class TestResult:
    __test__ = False

    passed: bool
    exit_code: int
    command: str
    stdout: str
    stderr: str
    duration_ms: int
    summary: str
    error_details: list[str]


class TestRunner:
    __test__ = False

    def __init__(self, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, command: str, working_dir: Union[str, Path]) -> TestResult:
        start = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=working_dir,
                check=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = _truncate_output(completed.stdout or "")
            stderr = _truncate_output(completed.stderr or "")
            passed = completed.returncode == 0
            summary = _build_summary(passed=passed, stdout=stdout)
            error_details = _extract_error_details(stdout=stdout, stderr=stderr)
            return TestResult(
                passed=passed,
                exit_code=completed.returncode,
                command=command,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                summary=summary,
                error_details=error_details,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = _truncate_output(exc.stdout or "")
            stderr = _truncate_output(exc.stderr or "")
            return TestResult(
                passed=False,
                exit_code=-1,
                command=command,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                summary=f"Test timed out after {self.timeout_seconds}s",
                error_details=["TIMEOUT"],
            )
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - start) * 1000)
            return TestResult(
                passed=False,
                exit_code=-1,
                command=command,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                summary="Test command not found",
                error_details=["COMMAND_NOT_FOUND"],
            )
        except Exception as exc:  # pragma: no cover - defensive
            duration_ms = int((time.monotonic() - start) * 1000)
            return TestResult(
                passed=False,
                exit_code=-1,
                command=command,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                summary=str(exc),
                error_details=[str(exc)],
            )


def _truncate_output(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    return text[:_OUTPUT_LIMIT] + _TRUNCATED_SUFFIX


def _build_summary(*, passed: bool, stdout: str) -> str:
    if passed:
        return "All tests passed"
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return "Tests failed"
    return " | ".join(lines[-3:])


def _extract_error_details(*, stdout: str, stderr: str) -> list[str]:
    details: list[str] = []
    for source in (stderr.splitlines(), stdout.splitlines()):
        for line in source:
            normalized = line.strip()
            if not normalized:
                continue
            upper = normalized.upper()
            if "FAILED" in upper or "ERROR" in upper:
                details.append(normalized)
    return details
