from __future__ import annotations

import re
from typing import Any

from pydantic import Field, model_validator

from .base import ContractRef, SEMVER_EXACT_PATTERN, StrictModel
from .evidence import CommandRecord


class ExecutionRequest(StrictModel):
    run_id: str
    role_id: str
    task_ref: ContractRef
    working_dir: str
    allowed_write: list[str]
    allowed_exec: list[str]
    prohibited_write: list[str]
    prohibited_exec: list[str]
    task_prompt: str
    injected_context: dict[str, Any]
    timeout_seconds: int = Field(default=300, gt=0)

    @model_validator(mode="after")
    def ensure_task_ref_exact(self) -> "ExecutionRequest":
        if not re.match(SEMVER_EXACT_PATTERN, self.task_ref.version):
            raise ValueError("ExecutionRequest.task_ref.version must be exact SemVer")
        return self


class ExecutionResult(StrictModel):
    success: bool
    exit_code: int | None = None
    modified_files: list[str] = Field(default_factory=list)
    commands_ran: list[CommandRecord] = Field(default_factory=list)
    agent_output: str = ""
    error_message: str | None = None
    duration_ms: int = Field(default=0, ge=0)

