from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, StrictModel
from .enums import ContractType


class Capabilities(StrictModel):
    read: list[str]
    write: list[str]
    exec: list[str]


class Prohibitions(StrictModel):
    write: list[str]
    exec: list[str]


class RetryPolicy(StrictModel):
    max_retries: int = Field(default=3, ge=0)


class RoleContractSpec(StrictModel):
    display_name: str
    capabilities: Capabilities
    prohibitions: Prohibitions
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class RoleContract(ContractEnvelope):
    meta: ContractMeta
    spec: RoleContractSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "RoleContract":
        if self.meta.type != ContractType.ROLE:
            raise ValueError("RoleContract meta.type must be 'role'")
        return self
