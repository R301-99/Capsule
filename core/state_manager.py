from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from .models.base import ContractRef, SEMVER_EXACT_PATTERN
from .models.enums import HumanTrigger
from .models.state import HumanQueueItem, ProjectState, ProjectStatus, RunRecord, RunStatus

_EXACT_SEMVER_PATTERN = re.compile(SEMVER_EXACT_PATTERN)
_TERMINAL_CURRENT_RUN_STATUSES = {RunStatus.PASSED, RunStatus.HALTED}


class StateLoadError(Exception):
    pass


class CheckpointNotFoundError(Exception):
    pass


class RunNotFoundError(Exception):
    pass


class HumanQueueItemNotFoundError(Exception):
    pass


class StateManager:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = Path(state_dir)

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    @property
    def project_state_path(self) -> Path:
        return self._state_dir / "PROJECT_STATE.json"

    @property
    def runs_dir(self) -> Path:
        return self._state_dir / "runs"

    @property
    def checkpoints_dir(self) -> Path:
        return self._state_dir / "checkpoints"

    @property
    def audit_dir(self) -> Path:
        return self._state_dir / "audit"

    @property
    def boundary_log_path(self) -> Path:
        return self.audit_dir / "boundary_violations.log"

    def init_project(self, project_id: str, conventions: dict[str, Any] | None = None) -> ProjectState:
        if self.project_state_path.exists():
            raise FileExistsError(f"PROJECT_STATE already exists: {self.project_state_path}")

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.boundary_log_path.touch(exist_ok=True)

        now = self._now_iso()
        state = ProjectState(
            project_id=project_id,
            global_conventions=conventions or {},
            created_at=now,
            updated_at=now,
        )
        self._write_json_atomic(self.project_state_path, state.model_dump(mode="json"))
        return state

    def load(self) -> ProjectState:
        if not self.project_state_path.exists():
            raise StateLoadError(f"PROJECT_STATE not found: {self.project_state_path}")
        try:
            raw = self.project_state_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateLoadError(f"Failed to read PROJECT_STATE: {exc}") from exc
        return self._parse_state(raw, context="PROJECT_STATE")

    def save(self, state: ProjectState) -> None:
        state.updated_at = self._now_iso()
        self._write_json_atomic(self.project_state_path, state.model_dump(mode="json"))

    def create_run(
        self, state: ProjectState, task_ref: ContractRef, role_id: str, node_id: str
    ) -> tuple[ProjectState, RunRecord]:
        if not _EXACT_SEMVER_PATTERN.match(task_ref.version):
            raise ValueError("create_run requires an exact task_ref version")

        run_id = self._build_id(prefix=None)
        run_record = RunRecord(
            run_id=run_id,
            task_ref=task_ref,
            role_id=role_id,
            node_id=node_id,
            status=RunStatus.PENDING,
            started_at=self._now_iso(),
            retry_count=0,
        )
        run_root = self.run_dir(run_id)
        (run_root / "gate_reports").mkdir(parents=True, exist_ok=True)
        (run_root / "rejections").mkdir(parents=True, exist_ok=True)
        (run_root / "human_decisions").mkdir(parents=True, exist_ok=True)

        state.run_history.append(run_record)
        state.status = ProjectStatus.RUNNING
        state.current_task_ref = task_ref
        state.current_node_id = node_id
        return state, run_record

    def update_run_status(
        self,
        state: ProjectState,
        run_id: str,
        new_status: RunStatus,
        *,
        finished_at: str | None = None,
        evidence_path: str | None = None,
        input_gate_path: str | None = None,
        output_gate_path: str | None = None,
    ) -> ProjectState:
        run = self._require_run(state, run_id)
        run.status = new_status
        if finished_at is not None:
            run.finished_at = finished_at
        if evidence_path is not None:
            run.evidence_path = evidence_path
        if input_gate_path is not None:
            run.input_gate_path = input_gate_path
        if output_gate_path is not None:
            run.output_gate_path = output_gate_path
        return state

    def increment_retry(self, state: ProjectState, run_id: str) -> ProjectState:
        run = self._require_run(state, run_id)
        run.retry_count += 1
        return state

    def write_gate_report(self, run_id: str, gate_id: str, report: dict[str, Any]) -> Path:
        run_root = self._require_run_dir(run_id)
        file_name = self._gate_report_file_name(gate_id)
        target_path = run_root / "gate_reports" / file_name
        self._write_json_atomic(target_path, report)
        return target_path

    def write_evidence(self, run_id: str, evidence: dict[str, Any]) -> Path:
        run_root = self._require_run_dir(run_id)
        target_path = run_root / "evidence.json"
        self._write_json_atomic(target_path, evidence)
        return target_path

    def write_rejection(self, run_id: str, rejection: dict[str, Any]) -> Path:
        run_root = self._require_run_dir(run_id)
        rejection_dir = run_root / "rejections"
        file_stem = self._preferred_file_stem(rejection, "rejection_id")
        if file_stem is None:
            file_stem = self._next_sequence_stem(rejection_dir, "rejection")
        target_path = rejection_dir / f"{file_stem}.json"
        self._write_json_atomic(target_path, rejection)
        return target_path

    def write_human_decision(self, run_id: str, decision: dict[str, Any]) -> Path:
        run_root = self._require_run_dir(run_id)
        decisions_dir = run_root / "human_decisions"
        file_stem = self._preferred_file_stem(decision, "decision_id")
        if file_stem is None:
            file_stem = self._next_sequence_stem(decisions_dir, "decision")
        target_path = decisions_dir / f"{file_stem}.json"
        self._write_json_atomic(target_path, decision)
        return target_path

    def append_boundary_violation(self, entry: str) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        line = f"[{self._now_iso()}] {entry}\n"
        with self.boundary_log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line)

    def save_checkpoint(self, state: ProjectState) -> str:
        checkpoint_id = self._build_id(prefix="ckpt")
        checkpoint_path = self.checkpoints_dir / f"{checkpoint_id}.json"
        self._write_json_atomic(checkpoint_path, state.model_dump(mode="json"))
        state.active_checkpoint_id = checkpoint_id
        return checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> ProjectState:
        checkpoint_path = self.checkpoints_dir / f"{checkpoint_id}.json"
        if not checkpoint_path.exists():
            raise CheckpointNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        try:
            raw = checkpoint_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateLoadError(f"Failed to read checkpoint {checkpoint_id}: {exc}") from exc
        return self._parse_state(raw, context=f"checkpoint:{checkpoint_id}")

    def list_checkpoints(self) -> list[str]:
        if not self.checkpoints_dir.exists():
            return []
        checkpoint_ids = [
            path.stem
            for path in self.checkpoints_dir.iterdir()
            if path.is_file() and path.suffix == ".json"
        ]
        return sorted(checkpoint_ids)

    def enqueue_human(
        self,
        state: ProjectState,
        run_id: str,
        trigger: HumanTrigger,
        summary: str,
        options: list[str],
    ) -> tuple[ProjectState, HumanQueueItem]:
        item = HumanQueueItem(
            item_id=self._build_id(prefix="hq"),
            run_id=run_id,
            trigger=trigger,
            summary=summary,
            options=list(options),
            created_at=self._now_iso(),
            resolved=False,
        )
        state.human_queue.append(item)
        state.status = ProjectStatus.WAITING_HUMAN
        return state, item

    def resolve_human(self, state: ProjectState, item_id: str, decision_id: str) -> ProjectState:
        matched_item: HumanQueueItem | None = None
        for item in state.human_queue:
            if item.item_id == item_id:
                matched_item = item
                break
        if matched_item is None:
            raise HumanQueueItemNotFoundError(f"Human queue item not found: {item_id}")

        matched_item.resolved = True
        matched_item.decision_id = decision_id
        if not self.pending_human_items(state):
            state.status = ProjectStatus.RUNNING
        return state

    def pending_human_items(self, state: ProjectState) -> list[HumanQueueItem]:
        return [item for item in state.human_queue if not item.resolved]

    def lock_refs(self, state: ProjectState, refs: list[ContractRef]) -> ProjectState:
        state.locked_refs = list(refs)
        return state

    def clear_locked_refs(self, state: ProjectState) -> ProjectState:
        state.locked_refs = []
        return state

    def current_run(self, state: ProjectState) -> RunRecord | None:
        for run in reversed(state.run_history):
            if run.status not in _TERMINAL_CURRENT_RUN_STATUSES:
                return run
        return None

    def get_run(self, state: ProjectState, run_id: str) -> RunRecord | None:
        for run in state.run_history:
            if run.run_id == run_id:
                return run
        return None

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def _require_run(self, state: ProjectState, run_id: str) -> RunRecord:
        run = self.get_run(state, run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")
        return run

    def _require_run_dir(self, run_id: str) -> Path:
        run_root = self.run_dir(run_id)
        if not run_root.exists() or not run_root.is_dir():
            raise RunNotFoundError(f"Run not found: {run_id}")
        return run_root

    @staticmethod
    def _preferred_file_stem(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _next_sequence_stem(directory: Path, prefix: str) -> str:
        directory.mkdir(parents=True, exist_ok=True)
        next_index = len([item for item in directory.iterdir() if item.is_file() and item.suffix == ".json"]) + 1
        return f"{prefix}-{next_index:04d}"

    @staticmethod
    def _gate_report_file_name(gate_id: str) -> str:
        normalized = gate_id.strip().lower()
        if normalized in {"input_gate", "input"}:
            return "input.json"
        if normalized in {"output_gate", "output"}:
            return "output.json"
        return f"{normalized}.json"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _build_id(prefix: str | None) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = uuid4().hex[:8]
        base = f"{stamp}-{suffix}"
        if prefix:
            return f"{prefix}-{base}"
        return base

    @staticmethod
    def _parse_state(raw: str, *, context: str) -> ProjectState:
        try:
            return ProjectState.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            raise StateLoadError(f"Failed to parse {context}: {exc}") from exc

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            tmp_path.write_text(encoded, encoding="utf-8")
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
