from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import StrictModel


class ExecutorConfig(StrictModel):
    type: str = "codex_cli"
    codex_command: str = "codex"
    timeout_seconds: int = Field(default=300, gt=0)


class TestRunnerConfig(StrictModel):
    timeout_seconds: int = Field(default=120, gt=0)


class CapsuleConfig(StrictModel):
    project_id: str
    workflow: str = "workflows/standard.yaml"
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    test_runner: TestRunnerConfig = Field(default_factory=TestRunnerConfig)
    global_conventions: dict[str, Any] = Field(default_factory=dict)

