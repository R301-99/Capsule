from __future__ import annotations

from .base import ContractRef, StrictModel
from .enums import GateId, GateLevel


class FailureDetails(StrictModel):
    summary: str
    errors: list[str]
    hint: str | None = None


class RejectionRecord(StrictModel):
    rejection_id: str
    target_role: str
    task_ref: ContractRef
    run_id: str
    retry_count: int
    max_retries: int
    failed_gate: GateId
    failed_level: GateLevel
    failed_contract_ref: ContractRef | None = None
    failure_details: FailureDetails
    created_at: str

