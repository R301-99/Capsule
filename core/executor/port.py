from __future__ import annotations

from abc import ABC, abstractmethod

from core.models.execution import ExecutionRequest, ExecutionResult


class ExecutorPort(ABC):
    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Execute one agent task request.

        Implementations must never raise; they should always return ExecutionResult,
        including failures and internal errors.
        """
        raise NotImplementedError

