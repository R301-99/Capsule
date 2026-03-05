from __future__ import annotations

from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, ContractRef, ROLE_ID_PATTERN, StrictModel
from .enums import ContractType


class TaskScope(StrictModel):
    include: list[str]
    exclude: list[str]
    create_allowed: list[str]


class TaskAcceptance(StrictModel):
    behavior_ref: ContractRef
    interface_refs: list[ContractRef]
    max_new_files: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_ref_types(self) -> "TaskAcceptance":
        if not self.behavior_ref.id.startswith("behavior."):
            raise ValueError("acceptance.behavior_ref.id must start with 'behavior.'")
        for interface_ref in self.interface_refs:
            if not interface_ref.id.startswith("interface."):
                raise ValueError("acceptance.interface_refs[*].id must start with 'interface.'")
        return self


class TaskContractSpec(StrictModel):
    assigned_to: str = Field(pattern=ROLE_ID_PATTERN)
    scope: TaskScope
    acceptance: TaskAcceptance
    token_budget: int | None = Field(default=None, ge=0)


class TaskContract(ContractEnvelope):
    meta: ContractMeta
    spec: TaskContractSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "TaskContract":
        if self.meta.type != ContractType.TASK:
            raise ValueError("TaskContract meta.type must be 'task'")
        return self
