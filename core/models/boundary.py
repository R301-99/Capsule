from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope
from .enums import CheckMethod, ContractType, ViolationAction


class BoundaryRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    check_method: CheckMethod
    violation_action: ViolationAction
    description: str | None = None


class OnViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notify: str = "human"
    log_path: str


class BoundaryContractSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sacred_files: list[str] = Field(min_length=1)
    rules: list[BoundaryRule] = Field(min_length=1)
    on_violation: OnViolation


class BoundaryContract(ContractEnvelope[BoundaryContractSpec]):
    spec: BoundaryContractSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "BoundaryContract":
        if self.meta.type != ContractType.BOUNDARY:
            raise ValueError("meta.type must be 'boundary' for BoundaryContract")
        return self
