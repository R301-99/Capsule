from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope, ContractRef
from .enums import ContractType, HumanAction, HumanTrigger


class HumanDecisionActions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next: HumanAction


class HumanDecisionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    trigger: HumanTrigger
    context_refs: list[ContractRef] = Field(default_factory=list)
    options_presented: list[str] = Field(min_length=1)
    selected_option: str
    rationale: str | None = None
    actions: HumanDecisionActions
    timestamp: datetime
    made_by: str = "human"

    @model_validator(mode="after")
    def selected_option_in_options(self) -> "HumanDecisionSpec":
        if self.selected_option not in self.options_presented:
            raise ValueError("selected_option must exist in options_presented")
        return self


class HumanDecisionContract(ContractEnvelope[HumanDecisionSpec]):
    spec: HumanDecisionSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "HumanDecisionContract":
        if self.meta.type != ContractType.HUMAN_DECISION:
            raise ValueError("meta.type must be 'human_decision' for HumanDecisionContract")
        return self
