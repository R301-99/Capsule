from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import ContractEnvelope, ContractRef
from .enums import ContractType, GateId, GateResult


class Diagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class GateReportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: GateId
    level: Literal[0, 1, 2, 3]
    result: GateResult
    failed_contract_ref: ContractRef | None = None
    diagnostics: Diagnostics
    resolved_refs: list[ContractRef] = Field(default_factory=list)
    timestamp: datetime


class GateReportContract(ContractEnvelope[GateReportSpec]):
    spec: GateReportSpec

    @model_validator(mode="after")
    def validate_meta_type(self) -> "GateReportContract":
        if self.meta.type != ContractType.GATE_REPORT:
            raise ValueError("meta.type must be 'gate_report' for GateReportContract")
        return self
