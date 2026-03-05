from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ContractStatus, ContractType, CreatedBy, FailureAction, Severity

CONTRACT_ID_PATTERN = r"^(role|task|interface|behavior|boundary|gate_report|evidence|human_decision)\.\w+(?:\.\w+)*$"
CONTRACT_REF_ID_PATTERN = CONTRACT_ID_PATTERN
SEMVER_EXACT_PATTERN = r"^\d+\.\d+\.\d+$"
SEMVER_OR_MAJOR_X_PATTERN = r"^\d+\.(?:x|\d+\.\d+)$"
ROLE_ID_PATTERN = r"^role\.\w+(?:\.\w+)*$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractRef(StrictModel):
    id: str = Field(pattern=CONTRACT_REF_ID_PATTERN)
    version: str = Field(pattern=SEMVER_OR_MAJOR_X_PATTERN)


class CheckDecl(StrictModel):
    kind: Literal["script", "command"]
    id: str | None = None
    run: str | None = None

    @model_validator(mode="after")
    def validate_run_for_command(self) -> "CheckDecl":
        if self.kind == "command" and not self.run:
            raise ValueError("CheckDecl.run is required when kind is 'command'")
        return self


class ValidationDecl(StrictModel):
    schema: str
    checks: list[CheckDecl] = Field(default_factory=list)


class OnFailure(StrictModel):
    action: FailureAction
    max_retries: int = Field(default=3, ge=0)
    severity: Severity = Severity.MID


class ContractMeta(StrictModel):
    type: ContractType
    id: str = Field(pattern=CONTRACT_ID_PATTERN)
    version: str = Field(pattern=SEMVER_EXACT_PATTERN)
    status: ContractStatus
    created_by: CreatedBy
    created_at: datetime
    dependencies: list[ContractRef]
    validation: ValidationDecl
    on_failure: OnFailure
    description: str | None = None
    tags: list[str] | None = None


class ContractEnvelope(StrictModel):
    meta: ContractMeta
    spec: dict[str, Any]
    extensions: dict[str, Any] = Field(default_factory=dict)
