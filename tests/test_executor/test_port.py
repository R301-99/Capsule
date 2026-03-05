from __future__ import annotations

import pytest

from core.executor.port import ExecutorPort
from core.models.evidence import CommandRecord
from core.models.execution import ExecutionRequest, ExecutionResult


def test_executor_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        ExecutorPort()  # type: ignore[abstract]


def test_mock_executor_can_return_success(execution_request: ExecutionRequest) -> None:
    class MockExecutor(ExecutorPort):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                success=True,
                exit_code=0,
                modified_files=["src/backend/auth.py"],
                commands_ran=[CommandRecord(cmd="mock", exit_code=0, duration_ms=12)],
                agent_output="ok",
                duration_ms=12,
            )

    result = MockExecutor().execute(execution_request)
    assert result.success is True
    assert result.exit_code == 0
    assert result.modified_files == ["src/backend/auth.py"]
    assert result.error_message is None


def test_mock_executor_can_return_error(execution_request: ExecutionRequest) -> None:
    class MockExecutor(ExecutorPort):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                success=False,
                exit_code=None,
                modified_files=[],
                commands_ran=[CommandRecord(cmd="mock", exit_code=-1, duration_ms=5)],
                agent_output="",
                error_message="mock error",
                duration_ms=5,
            )

    result = MockExecutor().execute(execution_request)
    assert result.success is False
    assert result.error_message == "mock error"
    assert result.commands_ran[0].exit_code == -1

