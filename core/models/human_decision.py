from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, ContractRef, StrictModel
from .enums import ContractType, HumanAction, HumanTrigger


class DecisionAction(StrictModel):
    next: HumanAction


class HumanDecisionSpec(StrictModel):
    decision_id: str
    trigger: HumanTrigger
    context_refs: list[ContractRef]
    options_presented: list[str] = Field(min_length=1)
    selected_option: str
    rationale: str | None = None
    actions: DecisionAction
    timestamp: datetime
    made_by: str = "human"

    @model_validator(mode="after")
    def ensure_option_is_presented(self) -> "HumanDecisionSpec":
        if self.selected_option not in self.options_presented:
            raise ValueError("selected_option must be one of options_presented")
        return self


class HumanDecisionContract(ContractEnvelope):
    meta: ContractMeta
    spec: HumanDecisionSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "HumanDecisionContract":
        if self.meta.type != ContractType.HUMAN_DECISION:
            raise ValueError("HumanDecisionContract meta.type must be 'human_decision'")
        return self
