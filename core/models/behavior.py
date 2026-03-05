from __future__ import annotations

from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, StrictModel
from .enums import ContractType


class TestSuite(StrictModel):
    runner: str
    entry: str
    command: str


class TestCase(StrictModel):
    id: str
    description: str
    must_pass: bool = True


class CoverageRequirement(StrictModel):
    minimum_percent: int = Field(ge=0, le=100)


class BehaviorContractSpec(StrictModel):
    test_suite: TestSuite
    mandatory_cases: list[TestCase] = Field(default_factory=list)
    coverage: CoverageRequirement | None = None


class BehaviorContract(ContractEnvelope):
    meta: ContractMeta
    spec: BehaviorContractSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "BehaviorContract":
        if self.meta.type != ContractType.BEHAVIOR:
            raise ValueError("BehaviorContract meta.type must be 'behavior'")
        return self
