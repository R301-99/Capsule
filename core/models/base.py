from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .enums import ContractStatus, ContractType, CreatedBy, FailureAction, Severity

REF_ID_PATTERN = r"^(role|task|interface|behavior|boundary)\.\w+(\.\w+)*$"
META_ID_PATTERN = r"^(role|task|interface|behavior|boundary|gate_report|evidence|human_decision)\.\w+(\.\w+)*$"
REF_VERSION_PATTERN = r"^\d+\.(x|\d+\.\d+)$"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class ContractRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=REF_ID_PATTERN)
    version: str = Field(pattern=REF_VERSION_PATTERN)


class CheckDecl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["script", "command"]
    id: str | None = None
    run: str | None = None


class ValidationDecl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: str
    checks: list[CheckDecl] = Field(default_factory=list)


class OnFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: FailureAction
    max_retries: int = Field(default=3, ge=0)
    severity: Severity = Severity.MID


class ContractMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ContractType
    id: str = Field(pattern=META_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    status: ContractStatus
    created_by: CreatedBy
    created_at: datetime
    dependencies: list[ContractRef] = Field(default_factory=list)
    validation: ValidationDecl
    on_failure: OnFailure
    description: str | None = None
    tags: list[str] | None = None


SpecT = TypeVar("SpecT", bound=BaseModel | dict[str, Any])


class ContractEnvelope(BaseModel, Generic[SpecT]):
    model_config = ConfigDict(extra="forbid")

    meta: ContractMeta
    spec: SpecT
    extensions: dict[str, Any] = Field(default_factory=dict)


class GenericContractEnvelope(ContractEnvelope[dict[str, Any]]):
    spec: dict[str, Any]
