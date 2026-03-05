from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from .base import ContractRef, StrictModel
from .enums import HumanTrigger


class ProjectStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class RunStatus(str, Enum):
    PENDING = "pending"
    INPUT_GATE = "input_gate"
    EXECUTING = "executing"
    OUTPUT_GATE = "output_gate"
    PASSED = "passed"
    FAILED = "failed"
    HALTED = "halted"
    WAITING_HUMAN = "waiting_human"


class RunRecord(StrictModel):
    run_id: str
    task_ref: ContractRef
    role_id: str
    node_id: str
    status: RunStatus
    evidence_path: str | None = None
    input_gate_path: str | None = None
    output_gate_path: str | None = None
    started_at: str
    finished_at: str | None = None
    retry_count: int = 0


class HumanQueueItem(StrictModel):
    item_id: str
    run_id: str
    trigger: HumanTrigger
    summary: str
    options: list[str] = Field(default_factory=list)
    created_at: str
    resolved: bool = False
    decision_id: str | None = None


class ProjectState(StrictModel):
    project_id: str
    current_workflow_id: str | None = None
    current_node_id: str | None = None
    current_task_ref: ContractRef | None = None
    phase: str = "init"
    status: ProjectStatus = ProjectStatus.IDLE
    locked_refs: list[ContractRef] = Field(default_factory=list)
    run_history: list[RunRecord] = Field(default_factory=list)
    active_checkpoint_id: str | None = None
    human_queue: list[HumanQueueItem] = Field(default_factory=list)
    global_conventions: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

