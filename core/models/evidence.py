from __future__ import annotations

import re

from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, ContractRef, SEMVER_EXACT_PATTERN, StrictModel
from .enums import ContractType, TestSummary


class ContractSnapshot(StrictModel):
    refs: list[ContractRef]


class DiffStat(StrictModel):
    files: int
    insertions: int
    deletions: int


class Changes(StrictModel):
    modified_files: list[str]
    diff_stat: DiffStat


class CommandRecord(StrictModel):
    cmd: str
    exit_code: int
    duration_ms: int | None = Field(default=None, ge=0)


class Commands(StrictModel):
    ran: list[CommandRecord]


class Tests(StrictModel):
    ran: list[CommandRecord]
    summary: TestSummary


class SelfReport(StrictModel):
    confidence: float = Field(ge=0.0, le=1.0)
    risks: list[str]
    notes: str | None = None


class ExecutionEvidenceSpec(StrictModel):
    run_id: str
    role_id: str
    task_ref: ContractRef
    contract_snapshot: ContractSnapshot
    changes: Changes
    commands: Commands
    tests: Tests
    self_report: SelfReport

    @model_validator(mode="after")
    def ensure_task_ref_exact(self) -> "ExecutionEvidenceSpec":
        if not re.match(SEMVER_EXACT_PATTERN, self.task_ref.version):
            raise ValueError("ExecutionEvidenceSpec.task_ref.version must be exact SemVer")
        return self


class EvidenceContract(ContractEnvelope):
    meta: ContractMeta
    spec: ExecutionEvidenceSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "EvidenceContract":
        if self.meta.type != ContractType.EVIDENCE:
            raise ValueError("EvidenceContract meta.type must be 'evidence'")
        return self
