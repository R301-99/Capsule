from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import ContractEnvelope, ContractMeta, ContractRef, StrictModel
from .enums import ContractType, GateId, GateLevel, GateResult


class Diagnostics(StrictModel):
    summary: str
    details: dict = Field(default_factory=dict)


class GateReportSpec(StrictModel):
    gate_id: GateId
    level: GateLevel
    result: GateResult
    failed_contract_ref: ContractRef | None = None
    diagnostics: Diagnostics
    resolved_refs: list[ContractRef]
    timestamp: datetime


class GateReportContract(ContractEnvelope):
    meta: ContractMeta
    spec: GateReportSpec

    @model_validator(mode="after")
    def ensure_meta_type(self) -> "GateReportContract":
        if self.meta.type != ContractType.GATE_REPORT:
            raise ValueError("GateReportContract meta.type must be 'gate_report'")
        return self
