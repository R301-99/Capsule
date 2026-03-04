from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope
from .enums import ContractType

ROLE_ID_PATTERN = r"^role\.\w+(\.\w+)*$"


class RequestDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: dict


class ResponseCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: int
    schema: dict


class ResponseDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: ResponseCase


class EndpointDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    method: str
    request: RequestDef
    response: ResponseDef


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producer: str = Field(pattern=ROLE_ID_PATTERN)
    consumers: list[str] = Field(default_factory=list)


class ChangePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_approval: list[str] = Field(min_length=1)
    on_change: str = "suspend_dependent_tasks"


class InterfaceContractSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[EndpointDef] = Field(min_length=1)
    binding: Binding
    change_policy: ChangePolicy


class InterfaceContract(ContractEnvelope[InterfaceContractSpec]):
    spec: InterfaceContractSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "InterfaceContract":
        if self.meta.type != ContractType.INTERFACE:
            raise ValueError("meta.type must be 'interface' for InterfaceContract")
        return self
