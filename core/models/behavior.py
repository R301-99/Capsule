from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope
from .enums import ContractType


class TestSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runner: str
    entry: str
    command: str


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    must_pass: bool = True


class CoverageRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_percent: int = Field(ge=0, le=100)


class BehaviorContractSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_suite: TestSuite
    mandatory_cases: list[TestCase] = Field(default_factory=list)
    coverage: CoverageRequirement | None = None


class BehaviorContract(ContractEnvelope[BehaviorContractSpec]):
    spec: BehaviorContractSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "BehaviorContract":
        if self.meta.type != ContractType.BEHAVIOR:
            raise ValueError("meta.type must be 'behavior' for BehaviorContract")
        return self
