from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope, ContractRef
from .enums import ContractType

ROLE_ID_PATTERN = r"^role\.\w+(\.\w+)*$"


class TaskScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include: list[str]
    exclude: list[str] = Field(default_factory=list)
    create_allowed: list[str] = Field(default_factory=list)


class TaskAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    behavior_ref: ContractRef
    interface_refs: list[ContractRef] = Field(default_factory=list)
    max_new_files: int = Field(ge=0)


class TaskContractSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to: str = Field(pattern=ROLE_ID_PATTERN)
    scope: TaskScope
    acceptance: TaskAcceptance
    token_budget: int | None = Field(default=None, ge=0)


class TaskContract(ContractEnvelope[TaskContractSpec]):
    spec: TaskContractSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "TaskContract":
        if self.meta.type != ContractType.TASK:
            raise ValueError("meta.type must be 'task' for TaskContract")
        return self
