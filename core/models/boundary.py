from __future__ import annotations

from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, StrictModel
from .enums import CheckMethod, ContractType, ViolationAction


class BoundaryRule(StrictModel):
    id: str
    check_method: CheckMethod
    violation_action: ViolationAction
    description: str | None = None


class OnViolation(StrictModel):
    notify: str = "human"
    log_path: str


class BoundaryContractSpec(StrictModel):
    sacred_files: list[str] = Field(min_length=1)
    rules: list[BoundaryRule] = Field(min_length=1)
    on_violation: OnViolation


class BoundaryContract(ContractEnvelope):
    meta: ContractMeta
    spec: BoundaryContractSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "BoundaryContract":
        if self.meta.type != ContractType.BOUNDARY:
            raise ValueError("BoundaryContract meta.type must be 'boundary'")
        return self
