from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .executor.evidence_builder import build_evidence
from .executor.port import ExecutorPort
from .models.base import ContractRef
from .models.behavior import BehaviorContract
from .models.enums import HumanTrigger
from .models.execution import ExecutionRequest
from .models.interface import InterfaceContract
from .models.role import RoleContract
from .models.state import HumanQueueItem, ProjectState, ProjectStatus, RunRecord, RunStatus
from .models.task import TaskContract
from .models.workflow import WorkflowDef, WorkflowNode
from .prompt_builder import build_prompt
from .registry import Registry, ResolutionError
from .state_manager import StateManager
from .test_runner import TestRunner
from .validator import Validator


@dataclass(frozen=True)
class OrchestratorResult:
    status: str
    current_node_id: str | None
    runs_executed: int
    human_items: list[HumanQueueItem]
    error_message: str | None = None


class Orchestrator:
    def __init__(
        self,
        registry: Registry,
        state_manager: StateManager,
        validator: Validator,
        executor: ExecutorPort,
        test_runner: TestRunner,
        project_root: Path,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._state_manager = state_manager
        self._validator = validator
        self._executor = executor
        self._test_runner = test_runner
        self._project_root = Path(project_root)
        self._on_event = on_event

    def load_workflow(self, workflow_path: Path) -> WorkflowDef:
        raw = yaml.safe_load(Path(workflow_path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Workflow YAML must decode into a mapping")
        payload = raw.get("workflow", raw)
        return WorkflowDef(**payload)

    def run(self, workflow: WorkflowDef, task_ref: ContractRef) -> OrchestratorResult:
        try:
            state = self._state_manager.load()
            state.current_workflow_id = workflow.id
            state.current_task_ref = task_ref
            self._state_manager.save(state)

            start_index = self._determine_start_index(state, workflow)
            runs_executed = 0

            for node in workflow.nodes[start_index:]:
                state.current_node_id = node.id
                state.status = ProjectStatus.RUNNING
                self._state_manager.save(state)

                state, outcome, error_message = self._execute_node(state, node, task_ref)
                runs_executed += 1

                if outcome == "waiting_human":
                    self._state_manager.save_checkpoint(state)
                    self._state_manager.save(state)
                    return OrchestratorResult(
                        status="waiting_human",
                        current_node_id=node.id,
                        runs_executed=runs_executed,
                        human_items=self._state_manager.pending_human_items(state),
                    )

                if outcome == "halted":
                    self._state_manager.save_checkpoint(state)
                    self._state_manager.save(state)
                    return OrchestratorResult(
                        status="halted",
                        current_node_id=node.id,
                        runs_executed=runs_executed,
                        human_items=self._state_manager.pending_human_items(state),
                    )

                if outcome == "error":
                    state.status = ProjectStatus.ERROR
                    self._state_manager.save(state)
                    return OrchestratorResult(
                        status="error",
                        current_node_id=node.id,
                        runs_executed=runs_executed,
                        human_items=self._state_manager.pending_human_items(state),
                        error_message=error_message,
                    )

            state.status = ProjectStatus.COMPLETED
            state.current_node_id = None
            self._state_manager.save(state)
            return OrchestratorResult(
                status="completed",
                current_node_id=None,
                runs_executed=runs_executed,
                human_items=self._state_manager.pending_human_items(state),
            )
        except Exception as exc:  # pragma: no cover - defensive
            return OrchestratorResult(
                status="error",
                current_node_id=None,
                runs_executed=0,
                human_items=[],
                error_message=str(exc),
            )

    def resume(self, workflow: WorkflowDef) -> OrchestratorResult:
        state = self._state_manager.load()
        if state.status not in {ProjectStatus.WAITING_HUMAN, ProjectStatus.PAUSED, ProjectStatus.RUNNING}:
            raise ValueError(f"Cannot resume: state.status is {state.status}")

        pending_items = self._state_manager.pending_human_items(state)
        if pending_items:
            raise ValueError(f"Cannot resume: {len(pending_items)} unresolved human items")

        if state.current_task_ref is None:
            raise ValueError("Cannot resume: state.current_task_ref is None")

        state.status = ProjectStatus.RUNNING
        self._state_manager.save(state)
        return self.run(workflow, state.current_task_ref)

    def _execute_node(
        self,
        state: ProjectState,
        node: WorkflowNode,
        task_ref: ContractRef,
    ) -> tuple[ProjectState, str, str | None]:
        self._emit("node_start", {"node_id": node.id, "role_id": node.role})
        input_result = self._validator.input_gate(state, task_ref, node.role)
        self._emit(
            "input_gate",
            {"passed": input_result.passed, "refs_count": len(input_result.resolved_refs)},
        )
        if not input_result.passed:
            summary = input_result.gate_report.get("diagnostics", {}).get("summary", "INPUT GATE failed")
            state, _ = self._state_manager.enqueue_human(
                state=state,
                run_id="n/a",
                trigger=HumanTrigger.REVIEW_REQUIRED,
                summary=f"INPUT GATE failed: {summary}",
                options=["approve", "amend_contract", "pause", "abort"],
            )
            state.status = ProjectStatus.WAITING_HUMAN
            self._state_manager.save(state)
            self._emit("human_gate", {"trigger": HumanTrigger.REVIEW_REQUIRED.value, "node_id": node.id})
            return state, "waiting_human", None

        state = self._state_manager.lock_refs(state, input_result.resolved_refs)

        task_contract = self._resolve_task_contract(task_ref)
        role_contract = self._resolve_role_contract(node.role)
        if task_contract is None or role_contract is None:
            state, _ = self._state_manager.enqueue_human(
                state=state,
                run_id="n/a",
                trigger=HumanTrigger.REVIEW_REQUIRED,
                summary="Contract context unavailable after INPUT GATE",
                options=["approve", "amend_contract", "pause", "abort"],
            )
            state.status = ProjectStatus.WAITING_HUMAN
            self._state_manager.save(state)
            return state, "waiting_human", None

        behavior_contract, interface_contracts = self._resolve_contract_context(input_result.resolved_refs)
        if behavior_contract is None:
            return state, "error", "Resolved refs do not contain behavior contract"

        max_retries = self._resolve_max_retries(task_contract, role_contract)
        state, run = self._state_manager.create_run(state, task_ref, node.role, node.id)
        state = self._state_manager.update_run_status(state, run.run_id, RunStatus.EXECUTING)
        self._state_manager.save(state)
        self._state_manager.write_gate_report(run.run_id, "INPUT_GATE", input_result.gate_report)

        rejection_history: list[dict[str, Any]] = []
        retry_count = 0

        while True:
            prompt = build_prompt(
                node=node,
                task_contract=task_contract.model_dump(mode="json"),
                interface_contracts=[contract.model_dump(mode="json") for contract in interface_contracts],
                behavior_contract=behavior_contract.model_dump(mode="json"),
                role_contract=role_contract.model_dump(mode="json"),
                state_snapshot=self._state_snapshot(state, run),
                rejection_history=rejection_history or None,
            )
            request = self._build_execution_request(
                run=run,
                task_ref=task_ref,
                role_contract=role_contract,
                prompt=prompt,
                state=state,
                rejection_history=rejection_history,
            )
            self._emit("executing", {"node_id": node.id, "run_id": run.run_id, "retry": retry_count})
            exec_result = self._executor.execute(request)
            self._emit(
                "execution_done",
                {
                    "node_id": node.id,
                    "run_id": run.run_id,
                    "success": exec_result.success,
                    "duration_ms": exec_result.duration_ms,
                },
            )

            evidence = build_evidence(request, exec_result, input_result.resolved_refs)
            self._state_manager.write_evidence(run.run_id, evidence)

            commands_ran = self._extract_command_strings(exec_result.commands_ran)
            gate_result = self._validator.output_gate(
                state=state,
                run_id=run.run_id,
                evidence=evidence,
                modified_files=exec_result.modified_files,
                commands_ran=commands_ran,
                test_runner=self._test_runner,
                working_dir=self._project_root,
            )
            self._state_manager.write_gate_report(run.run_id, "OUTPUT_GATE", gate_result.gate_report)
            self._emit(
                "output_gate_level",
                {
                    "node_id": node.id,
                    "run_id": run.run_id,
                    "level": gate_result.gate_report.get("level"),
                    "result": gate_result.gate_report.get("result"),
                    "l2": gate_result.l2_result,
                },
            )

            if gate_result.halt:
                state = self._state_manager.update_run_status(
                    state=state,
                    run_id=run.run_id,
                    new_status=RunStatus.HALTED,
                    finished_at=self._now_iso(),
                )
                for violation in gate_result.boundary_violations:
                    self._state_manager.append_boundary_violation(violation)
                state, _ = self._state_manager.enqueue_human(
                    state=state,
                    run_id=run.run_id,
                    trigger=HumanTrigger.BOUNDARY_VIOLATION,
                    summary="L3 boundary violation detected",
                    options=["abort", "amend_contract"],
                )
                state.status = ProjectStatus.WAITING_HUMAN
                self._state_manager.save(state)
                self._emit("human_gate", {"trigger": HumanTrigger.BOUNDARY_VIOLATION.value, "node_id": node.id})
                return state, "halted", None

            if gate_result.passed:
                state = self._state_manager.update_run_status(
                    state=state,
                    run_id=run.run_id,
                    new_status=RunStatus.PASSED,
                    finished_at=self._now_iso(),
                )
                self._state_manager.save(state)
                self._emit("node_passed", {"node_id": node.id, "run_id": run.run_id})

                if node.human_review:
                    state, _ = self._state_manager.enqueue_human(
                        state=state,
                        run_id=run.run_id,
                        trigger=HumanTrigger.REVIEW_REQUIRED,
                        summary=f"Node '{node.id}' completed, awaiting human review",
                        options=["approve", "amend_contract", "pause", "abort"],
                    )
                    state.status = ProjectStatus.WAITING_HUMAN
                    self._state_manager.save(state)
                    self._emit("human_gate", {"trigger": HumanTrigger.REVIEW_REQUIRED.value, "node_id": node.id})
                    return state, "waiting_human", None
                return state, "passed", None

            retry_count += 1
            self._emit(
                "node_failed",
                {
                    "node_id": node.id,
                    "run_id": run.run_id,
                    "retry": retry_count,
                    "level": gate_result.gate_report.get("level"),
                },
            )
            state = self._state_manager.update_run_status(state, run.run_id, RunStatus.FAILED)
            state = self._state_manager.increment_retry(state, run.run_id)
            if gate_result.rejection is not None:
                rejection_payload = gate_result.rejection.model_dump(mode="json")
                self._state_manager.write_rejection(run.run_id, rejection_payload)
                rejection_history.append(rejection_payload)

            if retry_count > max_retries:
                state = self._state_manager.update_run_status(state, run.run_id, RunStatus.WAITING_HUMAN)
                state, _ = self._state_manager.enqueue_human(
                    state=state,
                    run_id=run.run_id,
                    trigger=HumanTrigger.RETRY_EXCEEDED,
                    summary=f"Failed after {retry_count} retries",
                    options=["approve", "amend_contract", "pause", "abort"],
                )
                state.status = ProjectStatus.WAITING_HUMAN
                self._state_manager.save(state)
                self._emit("breaker", {"node_id": node.id, "retries": retry_count})
                self._emit("human_gate", {"trigger": HumanTrigger.RETRY_EXCEEDED.value, "node_id": node.id})
                return state, "waiting_human", None

            self._state_manager.save(state)

    @staticmethod
    def _resolve_max_retries(task_contract: TaskContract | None, role_contract: RoleContract | None) -> int:
        if task_contract is not None:
            return task_contract.meta.on_failure.max_retries
        if role_contract is not None:
            return role_contract.spec.retry_policy.max_retries
        return 3

    def _determine_start_index(self, state: ProjectState, workflow: WorkflowDef) -> int:
        if state.current_node_id is None:
            return 0
        for index, node in enumerate(workflow.nodes):
            if node.id != state.current_node_id:
                continue
            latest_node_run = self._latest_run_for_node(state, node.id)
            if latest_node_run is not None and latest_node_run.status == RunStatus.PASSED:
                return index + 1
            return index
        return 0

    @staticmethod
    def _latest_run_for_node(state: ProjectState, node_id: str) -> RunRecord | None:
        for run in reversed(state.run_history):
            if run.node_id == node_id:
                return run
        return None

    def _resolve_task_contract(self, task_ref: ContractRef) -> TaskContract | None:
        try:
            resolved = self._registry.resolve(task_ref)
        except ResolutionError:
            return None
        if isinstance(resolved, TaskContract):
            return resolved
        return None

    def _resolve_role_contract(self, role_id: str) -> RoleContract | None:
        resolved = self._registry.get_latest_active(role_id)
        if isinstance(resolved, RoleContract):
            return resolved
        return None

    def _resolve_contract_context(
        self, resolved_refs: list[ContractRef]
    ) -> tuple[BehaviorContract | None, list[InterfaceContract]]:
        behavior_contract: BehaviorContract | None = None
        interface_contracts: list[InterfaceContract] = []
        for ref in resolved_refs:
            try:
                resolved = self._registry.resolve(ref)
            except ResolutionError:
                continue
            if isinstance(resolved, BehaviorContract):
                behavior_contract = resolved
            elif isinstance(resolved, InterfaceContract):
                interface_contracts.append(resolved)
        return behavior_contract, interface_contracts

    def _build_execution_request(
        self,
        *,
        run: RunRecord,
        task_ref: ContractRef,
        role_contract: RoleContract,
        prompt: str,
        state: ProjectState,
        rejection_history: list[dict[str, Any]],
    ) -> ExecutionRequest:
        return ExecutionRequest(
            run_id=run.run_id,
            role_id=run.role_id,
            task_ref=task_ref,
            working_dir=str(self._project_root),
            allowed_write=list(role_contract.spec.capabilities.write),
            allowed_exec=list(role_contract.spec.capabilities.exec),
            prohibited_write=list(role_contract.spec.prohibitions.write),
            prohibited_exec=list(role_contract.spec.prohibitions.exec),
            task_prompt=prompt,
            injected_context={
                "workflow_id": state.current_workflow_id,
                "node_id": run.node_id,
                "state": self._state_snapshot(state, run),
                "rejection_history": rejection_history,
            },
        )

    @staticmethod
    def _extract_command_strings(commands_ran: list[Any]) -> list[str]:
        normalized: list[str] = []
        for item in commands_ran:
            command = None
            if isinstance(item, dict):
                command = item.get("cmd")
            elif hasattr(item, "cmd"):
                command = getattr(item, "cmd")
            elif isinstance(item, str):
                command = item
            if not isinstance(command, str):
                continue
            command = command.strip()
            if not command:
                continue
            # v0.1 executor may only log wrapper command; skip it to avoid false L3 positives.
            if command.startswith("codex exec") or command == "codex":
                continue
            normalized.append(command)
        return normalized

    @staticmethod
    def _state_snapshot(state: ProjectState, run: RunRecord) -> dict[str, Any]:
        return {
            "project_id": state.project_id,
            "phase": state.phase,
            "status": state.status.value if hasattr(state.status, "value") else str(state.status),
            "current_workflow_id": state.current_workflow_id,
            "current_node_id": state.current_node_id,
            "run_id": run.run_id,
            "retry_count": run.retry_count,
            "locked_refs": [ref.model_dump(mode="json") for ref in state.locked_refs],
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, data)
        except Exception:
            return
