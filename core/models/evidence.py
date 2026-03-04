from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope, ContractRef, SEMVER_PATTERN
from .enums import ContractType, TestSummary

ROLE_ID_PATTERN = r"^role\.\w+(\.\w+)*$"


class ContractSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refs: list[ContractRef]


class DiffStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: int = Field(ge=0)
    insertions: int = Field(ge=0)
    deletions: int = Field(ge=0)


class Changes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modified_files: list[str] = Field(default_factory=list)
    diff_stat: DiffStat


class CommandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cmd: str
    exit_code: int
    duration_ms: int | None = Field(default=None, ge=0)


class Commands(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ran: list[CommandRecord] = Field(default_factory=list)


class Tests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ran: list[CommandRecord] = Field(default_factory=list)
    summary: TestSummary


class SelfReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0)
    risks: list[str] = Field(default_factory=list)
    notes: str | None = None


class ExactContractRef(ContractRef):
    version: str = Field(pattern=SEMVER_PATTERN)


class ExecutionEvidenceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    role_id: str = Field(pattern=ROLE_ID_PATTERN)
    task_ref: ExactContractRef
    contract_snapshot: ContractSnapshot
    changes: Changes
    commands: Commands
    tests: Tests
    self_report: SelfReport


class EvidenceContract(ContractEnvelope[ExecutionEvidenceSpec]):
    spec: ExecutionEvidenceSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "EvidenceContract":
        if self.meta.type != ContractType.EVIDENCE:
            raise ValueError("meta.type must be 'evidence' for EvidenceContract")
        return self
