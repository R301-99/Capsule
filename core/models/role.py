from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope
from .enums import ContractType


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)
    exec: list[str] = Field(default_factory=list)


class Prohibitions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    write: list[str] = Field(default_factory=list)
    exec: list[str] = Field(default_factory=list)


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=3, ge=0)


class RoleContractSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    capabilities: Capabilities
    prohibitions: Prohibitions
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class RoleContract(ContractEnvelope[RoleContractSpec]):
    spec: RoleContractSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "RoleContract":
        if self.meta.type != ContractType.ROLE:
            raise ValueError("meta.type must be 'role' for RoleContract")
        return self
