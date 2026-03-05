from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from .base import ContractEnvelope, ContractMeta, ROLE_ID_PATTERN, StrictModel
from .enums import ContractType

RoleId = Annotated[str, StringConstraints(pattern=ROLE_ID_PATTERN)]


class RequestDef(StrictModel):
    schema: dict


class ResponseCase(StrictModel):
    status: int
    schema: dict


class ResponseDef(StrictModel):
    success: ResponseCase


class EndpointDef(StrictModel):
    id: str
    path: str
    method: str = Field(pattern=r"^[A-Z]+$")
    request: RequestDef
    response: ResponseDef


class Binding(StrictModel):
    producer: RoleId
    consumers: list[RoleId]


class ChangePolicy(StrictModel):
    requires_approval: list[str] = Field(min_length=1)
    on_change: str = "suspend_dependent_tasks"


class InterfaceContractSpec(StrictModel):
    endpoints: list[EndpointDef] = Field(min_length=1)
    binding: Binding
    change_policy: ChangePolicy


class InterfaceContract(ContractEnvelope):
    meta: ContractMeta
    spec: InterfaceContractSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "InterfaceContract":
        if self.meta.type != ContractType.INTERFACE:
            raise ValueError("InterfaceContract meta.type must be 'interface'")
        return self
