from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path, PurePath
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import ValidationError

from .models.base import ContractRef
from .models.behavior import BehaviorContract
from .models.boundary import BoundaryContract
from .models.enums import ContractStatus, ContractType, GateId, GateLevel, GateResult
from .models.evidence import ExecutionEvidenceSpec
from .models.gate_report import GateReportSpec
from .models.rejection import FailureDetails, RejectionRecord
from .models.role import RoleContract
from .models.state import ProjectState
from .models.task import TaskContract
from .registry import Registry, ResolutionError
from .state_manager import StateManager
from .test_runner import TestRunner

_ALLOWED_BEHAVIOR_CREATORS = {"role.qa", "human"}


@dataclass(frozen=True)
class InputGateResult:
    passed: bool
    gate_report: dict[str, Any]
    resolved_refs: list[ContractRef]
    rejection: RejectionRecord | None


@dataclass(frozen=True)
class OutputGateResult:
    passed: bool
    gate_report: dict[str, Any]
    rejection: RejectionRecord | None
    halt: bool
    boundary_violations: list[str]
    l2_result: dict[str, Any] | None


class Validator:
    def __init__(self, registry: Registry, state_manager: StateManager) -> None:
        self._registry = registry
        self._state_manager = state_manager

    def input_gate(self, state: ProjectState, task_ref: ContractRef, role_id: str) -> InputGateResult:
        run_id = self._current_or_default_run_id(state)
        task_contract = self._resolve_task(task_ref)
        if task_contract is None:
            role_contract = self._resolve_role(role_id)
            report = self._make_gate_report(
                gate_id=GateId.INPUT_GATE,
                level=GateLevel.L0,
                result=GateResult.FAIL,
                resolved_refs=[],
                failed_contract_ref=task_ref,
                diagnostics_summary=f"Task contract not found: {task_ref.id}@{task_ref.version}",
                diagnostics_details={},
            )
            rejection = self._make_rejection(
                target_role=role_id,
                task_ref=task_ref,
                run_id=run_id,
                retry_count=self._retry_count(state, run_id),
                max_retries=self._resolve_max_retries(task_contract, role_contract),
                failed_gate=GateId.INPUT_GATE,
                failed_level=GateLevel.L0,
                failed_contract_ref=task_ref,
                summary="Task contract not found",
                errors=[f"Unable to resolve {task_ref.id}@{task_ref.version}"],
                hint="Ensure task contract exists and version reference is valid.",
            )
            self._write_input_report_if_run_exists(state, report)
            return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)

        role_contract = self._resolve_role(role_id)
        if role_contract is None:
            report = self._make_gate_report(
                gate_id=GateId.INPUT_GATE,
                level=GateLevel.L0,
                result=GateResult.FAIL,
                resolved_refs=[],
                failed_contract_ref=ContractRef(id=role_id, version="1.x"),
                diagnostics_summary=f"Role contract not found: {role_id}",
                diagnostics_details={},
            )
            rejection = self._make_rejection(
                target_role=role_id,
                task_ref=self._exact_ref(task_contract),
                run_id=run_id,
                retry_count=self._retry_count(state, run_id),
                max_retries=self._resolve_max_retries(task_contract, role_contract),
                failed_gate=GateId.INPUT_GATE,
                failed_level=GateLevel.L0,
                failed_contract_ref=ContractRef(id=role_id, version="1.x"),
                summary="Role contract not found",
                errors=[f"Unable to load latest active role for {role_id}"],
                hint="Ensure role contract exists with active status.",
            )
            self._write_input_report_if_run_exists(state, report)
            return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)

        active_boundaries = self._active_boundaries()
        if not active_boundaries:
            report = self._make_gate_report(
                gate_id=GateId.INPUT_GATE,
                level=GateLevel.L0,
                result=GateResult.FAIL,
                resolved_refs=[],
                failed_contract_ref=None,
                diagnostics_summary="No active boundary contracts found",
                diagnostics_details={},
            )
            rejection = self._make_rejection(
                target_role=role_id,
                task_ref=self._exact_ref(task_contract),
                run_id=run_id,
                retry_count=self._retry_count(state, run_id),
                max_retries=self._resolve_max_retries(task_contract, role_contract),
                failed_gate=GateId.INPUT_GATE,
                failed_level=GateLevel.L0,
                failed_contract_ref=None,
                summary="Boundary contracts missing",
                errors=["No active boundary contracts found in registry"],
                hint="Load at least one active boundary contract before execution.",
            )
            self._write_input_report_if_run_exists(state, report)
            return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)

        resolved_behavior = self._resolve_ref(task_contract.spec.acceptance.behavior_ref)
        if resolved_behavior is None or not isinstance(resolved_behavior, BehaviorContract):
            failed_ref = task_contract.spec.acceptance.behavior_ref
            report = self._make_gate_report(
                gate_id=GateId.INPUT_GATE,
                level=GateLevel.L1,
                result=GateResult.FAIL,
                resolved_refs=[self._exact_ref(task_contract)],
                failed_contract_ref=failed_ref,
                diagnostics_summary="Behavior dependency could not be resolved",
                diagnostics_details={"missing_ref": failed_ref.model_dump(mode="json")},
            )
            rejection = self._make_rejection(
                target_role=role_id,
                task_ref=self._exact_ref(task_contract),
                run_id=run_id,
                retry_count=self._retry_count(state, run_id),
                max_retries=self._resolve_max_retries(task_contract, role_contract),
                failed_gate=GateId.INPUT_GATE,
                failed_level=GateLevel.L1,
                failed_contract_ref=failed_ref,
                summary="Behavior dependency missing",
                errors=[f"Unable to resolve {failed_ref.id}@{failed_ref.version}"],
                hint="Publish an active behavior contract matching task acceptance.",
            )
            self._write_input_report_if_run_exists(state, report)
            return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)

        resolved_interfaces: list[ContractRef] = []
        for interface_ref in task_contract.spec.acceptance.interface_refs:
            resolved_interface = self._resolve_ref(interface_ref)
            if resolved_interface is None or resolved_interface.meta.type != ContractType.INTERFACE:
                report = self._make_gate_report(
                    gate_id=GateId.INPUT_GATE,
                    level=GateLevel.L1,
                    result=GateResult.FAIL,
                    resolved_refs=[self._exact_ref(task_contract), self._exact_ref(resolved_behavior)],
                    failed_contract_ref=interface_ref,
                    diagnostics_summary="Interface dependency could not be resolved",
                    diagnostics_details={"missing_ref": interface_ref.model_dump(mode="json")},
                )
                rejection = self._make_rejection(
                    target_role=role_id,
                    task_ref=self._exact_ref(task_contract),
                    run_id=run_id,
                    retry_count=self._retry_count(state, run_id),
                    max_retries=self._resolve_max_retries(task_contract, role_contract),
                    failed_gate=GateId.INPUT_GATE,
                    failed_level=GateLevel.L1,
                    failed_contract_ref=interface_ref,
                    summary="Interface dependency missing",
                    errors=[f"Unable to resolve {interface_ref.id}@{interface_ref.version}"],
                    hint="Publish required interface contract versions referenced by task acceptance.",
                )
                self._write_input_report_if_run_exists(state, report)
                return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)
            resolved_interfaces.append(self._exact_ref(resolved_interface))

        scope_errors: list[str] = []
        for include_pattern in task_contract.spec.scope.include:
            if not self._is_scope_covered(include_pattern, role_contract.spec.capabilities.write):
                scope_errors.append(f"Scope '{include_pattern}' is not covered by role write capabilities")
            if self._matches_any_prefix_rule(include_pattern, role_contract.spec.prohibitions.write):
                scope_errors.append(f"Scope '{include_pattern}' conflicts with role write prohibitions")
        if scope_errors:
            report = self._make_gate_report(
                gate_id=GateId.INPUT_GATE,
                level=GateLevel.L1,
                result=GateResult.FAIL,
                resolved_refs=[self._exact_ref(task_contract), self._exact_ref(resolved_behavior)] + resolved_interfaces,
                failed_contract_ref=self._exact_ref(role_contract),
                diagnostics_summary="Task scope is not permitted by role policy",
                diagnostics_details={"errors": scope_errors},
            )
            rejection = self._make_rejection(
                target_role=role_id,
                task_ref=self._exact_ref(task_contract),
                run_id=run_id,
                retry_count=self._retry_count(state, run_id),
                max_retries=self._resolve_max_retries(task_contract, role_contract),
                failed_gate=GateId.INPUT_GATE,
                failed_level=GateLevel.L1,
                failed_contract_ref=self._exact_ref(role_contract),
                summary="Scope authorization failed",
                errors=scope_errors,
                hint="Adjust task scope or role capabilities/prohibitions.",
            )
            self._write_input_report_if_run_exists(state, report)
            return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)

        if resolved_behavior.meta.created_by.value not in _ALLOWED_BEHAVIOR_CREATORS:
            report = self._make_gate_report(
                gate_id=GateId.INPUT_GATE,
                level=GateLevel.L1,
                result=GateResult.FAIL,
                resolved_refs=[self._exact_ref(task_contract), self._exact_ref(resolved_behavior)] + resolved_interfaces,
                failed_contract_ref=self._exact_ref(resolved_behavior),
                diagnostics_summary="Behavior created_by is not allowed for execution",
                diagnostics_details={"created_by": resolved_behavior.meta.created_by.value},
            )
            rejection = self._make_rejection(
                target_role=role_id,
                task_ref=self._exact_ref(task_contract),
                run_id=run_id,
                retry_count=self._retry_count(state, run_id),
                max_retries=self._resolve_max_retries(task_contract, role_contract),
                failed_gate=GateId.INPUT_GATE,
                failed_level=GateLevel.L1,
                failed_contract_ref=self._exact_ref(resolved_behavior),
                summary="Behavior provenance check failed",
                errors=[f"behavior.meta.created_by={resolved_behavior.meta.created_by.value} is not allowed"],
                hint="Behavior contract must be created by role.qa or human.",
            )
            self._write_input_report_if_run_exists(state, report)
            return InputGateResult(passed=False, gate_report=report, resolved_refs=[], rejection=rejection)

        resolved_refs = [self._exact_ref(task_contract), self._exact_ref(resolved_behavior)] + resolved_interfaces
        report = self._make_gate_report(
            gate_id=GateId.INPUT_GATE,
            level=GateLevel.L1,
            result=GateResult.PASS,
            resolved_refs=resolved_refs,
            failed_contract_ref=None,
            diagnostics_summary="Input gate checks passed",
            diagnostics_details={"resolved_count": len(resolved_refs)},
        )
        self._write_input_report_if_run_exists(state, report)
        return InputGateResult(passed=True, gate_report=report, resolved_refs=resolved_refs, rejection=None)

    def output_gate(
        self,
        state: ProjectState,
        run_id: str,
        evidence: dict[str, Any],
        modified_files: list[str],
        commands_ran: list[str],
        test_runner: TestRunner | None = None,
        working_dir: Optional[Union[str, Path]] = None,
    ) -> OutputGateResult:
        run = self._state_manager.get_run(state, run_id)
        if run is None:
            report = self._make_gate_report(
                gate_id=GateId.OUTPUT_GATE,
                level=GateLevel.L0,
                result=GateResult.FAIL,
                resolved_refs=list(state.locked_refs),
                failed_contract_ref=None,
                diagnostics_summary=f"Run not found: {run_id}",
                diagnostics_details={},
            )
            rejection = self._make_rejection(
                target_role="unknown",
                task_ref=state.current_task_ref or ContractRef(id="task.unknown", version="1.0.0"),
                run_id=run_id,
                retry_count=0,
                max_retries=3,
                failed_gate=GateId.OUTPUT_GATE,
                failed_level=GateLevel.L0,
                failed_contract_ref=None,
                summary="Run not found",
                errors=[f"run_id={run_id} does not exist in state.run_history"],
                hint="Create run before invoking output gate.",
            )
            return OutputGateResult(
                passed=False,
                gate_report=report,
                rejection=rejection,
                halt=False,
                boundary_violations=[],
                l2_result=self._l2_skipped("Pre-L2 failure"),
            )

        try:
            evidence_spec = ExecutionEvidenceSpec(**evidence)
        except ValidationError as exc:
            report = self._make_gate_report(
                gate_id=GateId.OUTPUT_GATE,
                level=GateLevel.L0,
                result=GateResult.FAIL,
                resolved_refs=list(state.locked_refs),
                failed_contract_ref=state.current_task_ref,
                diagnostics_summary="Evidence payload failed L0 validation",
                diagnostics_details={"errors": exc.errors()},
            )
            rejection = self._make_rejection(
                target_role=run.role_id,
                task_ref=run.task_ref,
                run_id=run_id,
                retry_count=run.retry_count,
                max_retries=self._resolve_max_retries_for_refs(run.task_ref, run.role_id),
                failed_gate=GateId.OUTPUT_GATE,
                failed_level=GateLevel.L0,
                failed_contract_ref=state.current_task_ref,
                summary="Evidence schema validation failed",
                errors=[str(error) for error in exc.errors()],
                hint="Provide complete and valid execution evidence payload.",
            )
            self._state_manager.write_gate_report(run_id, GateId.OUTPUT_GATE.value, report)
            return OutputGateResult(
                passed=False,
                gate_report=report,
                rejection=rejection,
                halt=False,
                boundary_violations=[],
                l2_result=self._l2_skipped("Pre-L2 failure"),
            )

        if state.current_task_ref is None or not self._same_ref(evidence_spec.task_ref, state.current_task_ref):
            report = self._make_gate_report(
                gate_id=GateId.OUTPUT_GATE,
                level=GateLevel.L1,
                result=GateResult.FAIL,
                resolved_refs=list(state.locked_refs),
                failed_contract_ref=evidence_spec.task_ref,
                diagnostics_summary="Evidence task_ref does not match current task",
                diagnostics_details={
                    "evidence_task_ref": evidence_spec.task_ref.model_dump(mode="json"),
                    "state_current_task_ref": state.current_task_ref.model_dump(mode="json")
                    if state.current_task_ref is not None
                    else None,
                },
            )
            rejection = self._make_rejection(
                target_role=run.role_id,
                task_ref=run.task_ref,
                run_id=run_id,
                retry_count=run.retry_count,
                max_retries=self._resolve_max_retries_for_refs(run.task_ref, run.role_id),
                failed_gate=GateId.OUTPUT_GATE,
                failed_level=GateLevel.L1,
                failed_contract_ref=evidence_spec.task_ref,
                summary="Task reference mismatch",
                errors=["evidence.task_ref does not match state.current_task_ref"],
                hint="Regenerate evidence using the locked task reference.",
            )
            self._state_manager.write_gate_report(run_id, GateId.OUTPUT_GATE.value, report)
            return OutputGateResult(
                passed=False,
                gate_report=report,
                rejection=rejection,
                halt=False,
                boundary_violations=[],
                l2_result=self._l2_skipped("Pre-L2 failure"),
            )

        snapshot_pairs = {(item.id, item.version) for item in evidence_spec.contract_snapshot.refs}
        missing_locked = [ref for ref in state.locked_refs if (ref.id, ref.version) not in snapshot_pairs]
        if missing_locked:
            report = self._make_gate_report(
                gate_id=GateId.OUTPUT_GATE,
                level=GateLevel.L1,
                result=GateResult.FAIL,
                resolved_refs=list(state.locked_refs),
                failed_contract_ref=missing_locked[0],
                diagnostics_summary="Evidence contract snapshot is missing locked references",
                diagnostics_details={"missing_locked_refs": [ref.model_dump(mode="json") for ref in missing_locked]},
            )
            rejection = self._make_rejection(
                target_role=run.role_id,
                task_ref=run.task_ref,
                run_id=run_id,
                retry_count=run.retry_count,
                max_retries=self._resolve_max_retries_for_refs(run.task_ref, run.role_id),
                failed_gate=GateId.OUTPUT_GATE,
                failed_level=GateLevel.L1,
                failed_contract_ref=missing_locked[0],
                summary="Contract snapshot incomplete",
                errors=[f"Missing locked ref {ref.id}@{ref.version}" for ref in missing_locked],
                hint="Include all locked refs in evidence.contract_snapshot.refs.",
            )
            self._state_manager.write_gate_report(run_id, GateId.OUTPUT_GATE.value, report)
            return OutputGateResult(
                passed=False,
                gate_report=report,
                rejection=rejection,
                halt=False,
                boundary_violations=[],
                l2_result=self._l2_skipped("Pre-L2 failure"),
            )

        l2_result = self._l2_skipped("L2 runner not provided")
        l2_failed = False
        l2_failed_ref: ContractRef | None = None
        if test_runner is not None:
            resolved_behavior_ref = self._resolve_behavior_ref_for_l2(state=state, task_ref=run.task_ref)
            if resolved_behavior_ref is None:
                l2_result = {
                    "status": "failed",
                    "command": None,
                    "exit_code": -1,
                    "summary": "Behavior contract unavailable for L2 verification",
                    "error_details": ["Behavior reference could not be resolved"],
                    "duration_ms": 0,
                }
                l2_failed = True
            else:
                behavior_contract = self._resolve_ref(resolved_behavior_ref)
                if not isinstance(behavior_contract, BehaviorContract):
                    l2_result = {
                        "status": "failed",
                        "command": None,
                        "exit_code": -1,
                        "summary": "Behavior contract unavailable for L2 verification",
                        "error_details": [f"Unable to load behavior {resolved_behavior_ref.id}@{resolved_behavior_ref.version}"],
                        "duration_ms": 0,
                    }
                    l2_failed = True
                    l2_failed_ref = resolved_behavior_ref
                else:
                    effective_working_dir: Union[str, Path]
                    if working_dir is None:
                        effective_working_dir = self._state_manager.state_dir.parent
                    else:
                        effective_working_dir = working_dir
                    test_result = test_runner.run(
                        command=behavior_contract.spec.test_suite.command,
                        working_dir=effective_working_dir,
                    )
                    l2_result = {
                        "status": "passed" if test_result.passed else "failed",
                        "command": test_result.command,
                        "exit_code": test_result.exit_code,
                        "summary": test_result.summary,
                        "error_details": test_result.error_details,
                        "duration_ms": test_result.duration_ms,
                    }
                    l2_failed = not test_result.passed
                    l2_failed_ref = self._exact_ref(behavior_contract)

        boundary_violations = self._collect_boundary_violations(
            role_id=run.role_id,
            modified_files=modified_files,
            commands_ran=commands_ran,
        )
        if boundary_violations:
            report = self._make_gate_report(
                gate_id=GateId.OUTPUT_GATE,
                level=GateLevel.L3,
                result=GateResult.HALT,
                resolved_refs=list(state.locked_refs),
                failed_contract_ref=None,
                diagnostics_summary="Boundary violations detected",
                diagnostics_details={"violations": boundary_violations, "l2": l2_result},
            )
            self._state_manager.write_gate_report(run_id, GateId.OUTPUT_GATE.value, report)
            return OutputGateResult(
                passed=False,
                gate_report=report,
                rejection=None,
                halt=True,
                boundary_violations=boundary_violations,
                l2_result=l2_result,
            )

        if l2_failed:
            report = self._make_gate_report(
                gate_id=GateId.OUTPUT_GATE,
                level=GateLevel.L2,
                result=GateResult.FAIL,
                resolved_refs=list(state.locked_refs),
                failed_contract_ref=l2_failed_ref,
                diagnostics_summary=f"L2 behavior verification failed: {l2_result.get('summary', 'tests failed')}",
                diagnostics_details={"l2": l2_result},
            )
            rejection = self._make_rejection(
                target_role=run.role_id,
                task_ref=run.task_ref,
                run_id=run_id,
                retry_count=run.retry_count,
                max_retries=self._resolve_max_retries_for_refs(run.task_ref, run.role_id),
                failed_gate=GateId.OUTPUT_GATE,
                failed_level=GateLevel.L2,
                failed_contract_ref=l2_failed_ref,
                summary="Behavior verification failed",
                errors=l2_result.get("error_details", []),
                hint="Fix failing tests declared by behavior contract before retrying.",
            )
            self._state_manager.write_gate_report(run_id, GateId.OUTPUT_GATE.value, report)
            return OutputGateResult(
                passed=False,
                gate_report=report,
                rejection=rejection,
                halt=False,
                boundary_violations=[],
                l2_result=l2_result,
            )

        report = self._make_gate_report(
            gate_id=GateId.OUTPUT_GATE,
            level=GateLevel.L3,
            result=GateResult.PASS,
            resolved_refs=list(state.locked_refs),
            failed_contract_ref=None,
            diagnostics_summary="Output gate checks passed",
            diagnostics_details={"l2": l2_result},
        )
        self._state_manager.write_gate_report(run_id, GateId.OUTPUT_GATE.value, report)
        return OutputGateResult(
            passed=True,
            gate_report=report,
            rejection=None,
            halt=False,
            boundary_violations=[],
            l2_result=l2_result,
        )

    def _resolve_task(self, task_ref: ContractRef) -> TaskContract | None:
        contract = self._resolve_ref(task_ref)
        if isinstance(contract, TaskContract):
            return contract
        return None

    def _resolve_role(self, role_id: str) -> RoleContract | None:
        role = self._registry.get_latest_active(role_id)
        if isinstance(role, RoleContract):
            return role
        return None

    def _resolve_ref(self, ref: ContractRef):
        try:
            return self._registry.resolve(ref)
        except ResolutionError:
            return None

    def _active_boundaries(self) -> list[BoundaryContract]:
        return [
            contract
            for contract in self._registry.list_by_type(ContractType.BOUNDARY)
            if isinstance(contract, BoundaryContract) and contract.meta.status == ContractStatus.ACTIVE
        ]

    def _resolve_max_retries(self, task_contract: TaskContract | None, role_contract: RoleContract | None) -> int:
        if task_contract is not None:
            return task_contract.meta.on_failure.max_retries
        if role_contract is not None:
            return role_contract.spec.retry_policy.max_retries
        return 3

    def _resolve_max_retries_for_refs(self, task_ref: ContractRef, role_id: str) -> int:
        task_contract = self._resolve_task(task_ref)
        role_contract = self._resolve_role(role_id)
        return self._resolve_max_retries(task_contract, role_contract)

    @staticmethod
    def _l2_skipped(reason: str) -> dict[str, Any]:
        return {
            "status": "skipped",
            "command": None,
            "exit_code": None,
            "summary": reason,
            "error_details": [],
            "duration_ms": 0,
        }

    def _resolve_behavior_ref_for_l2(self, *, state: ProjectState, task_ref: ContractRef) -> ContractRef | None:
        for ref in state.locked_refs:
            if ref.id.startswith("behavior."):
                return ref

        task_contract = self._resolve_task(task_ref)
        if task_contract is None:
            return None
        resolved = self._resolve_ref(task_contract.spec.acceptance.behavior_ref)
        if isinstance(resolved, BehaviorContract):
            return self._exact_ref(resolved)
        return None

    @staticmethod
    def _retry_count(state: ProjectState, run_id: str) -> int:
        if run_id == "n/a":
            return 0
        for run in state.run_history:
            if run.run_id == run_id:
                return run.retry_count
        return 0

    @staticmethod
    def _exact_ref(contract) -> ContractRef:
        return ContractRef(id=contract.meta.id, version=contract.meta.version)

    @staticmethod
    def _same_ref(left: ContractRef, right: ContractRef) -> bool:
        return left.id == right.id and left.version == right.version

    @staticmethod
    def _normalize_pattern_prefix(pattern: str) -> str:
        cleaned = pattern.strip()
        while cleaned.endswith("*"):
            cleaned = cleaned[:-1]
        return cleaned

    def _is_scope_covered(self, scope_pattern: str, capability_patterns: list[str]) -> bool:
        scope_prefix = self._normalize_pattern_prefix(scope_pattern)
        for capability in capability_patterns:
            cap_prefix = self._normalize_pattern_prefix(capability)
            if not cap_prefix:
                return True
            if scope_prefix.startswith(cap_prefix):
                return True
        return False

    def _matches_any_prefix_rule(self, scope_pattern: str, policy_patterns: list[str]) -> bool:
        scope_prefix = self._normalize_pattern_prefix(scope_pattern)
        for policy in policy_patterns:
            policy_prefix = self._normalize_pattern_prefix(policy)
            if not policy_prefix:
                return True
            if scope_prefix.startswith(policy_prefix) or policy_prefix.startswith(scope_prefix):
                return True
        return False

    def _collect_boundary_violations(
        self,
        *,
        role_id: str,
        modified_files: list[str],
        commands_ran: list[str],
    ) -> list[str]:
        violations: list[str] = []
        boundary_patterns: list[str] = []
        for boundary in self._active_boundaries():
            boundary_patterns.extend(boundary.spec.sacred_files)

        for file_path in modified_files:
            if path_matches_any_pattern(file_path, boundary_patterns):
                violations.append(f"Sacred file modified: {file_path}")

        role_contract = self._resolve_role(role_id)
        if role_contract is None:
            violations.append(f"Role contract unavailable for command audit: {role_id}")
            return violations

        for command in commands_ran:
            if command_matches_any_prefix(command, role_contract.spec.prohibitions.exec):
                violations.append(f"Command is explicitly prohibited: {command}")
                continue
            if not command_matches_any_prefix(command, role_contract.spec.capabilities.exec):
                violations.append(f"Command is outside role capabilities: {command}")
        return violations

    @staticmethod
    def _make_gate_report(
        *,
        gate_id: GateId,
        level: GateLevel,
        result: GateResult,
        resolved_refs: list[ContractRef],
        failed_contract_ref: ContractRef | None,
        diagnostics_summary: str,
        diagnostics_details: dict[str, Any] | None,
    ) -> dict[str, Any]:
        report = GateReportSpec(
            gate_id=gate_id,
            level=level,
            result=result,
            failed_contract_ref=failed_contract_ref,
            diagnostics={
                "summary": diagnostics_summary,
                "details": diagnostics_details or {},
            },
            resolved_refs=resolved_refs,
            timestamp=datetime.now(timezone.utc),
        )
        return report.model_dump(mode="json")

    @staticmethod
    def _make_rejection(
        *,
        target_role: str,
        task_ref: ContractRef,
        run_id: str,
        retry_count: int,
        max_retries: int,
        failed_gate: GateId,
        failed_level: GateLevel,
        failed_contract_ref: ContractRef | None,
        summary: str,
        errors: list[str],
        hint: str | None,
    ) -> RejectionRecord:
        rejection_id = f"rej-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        return RejectionRecord(
            rejection_id=rejection_id,
            target_role=target_role,
            task_ref=task_ref,
            run_id=run_id,
            retry_count=retry_count,
            max_retries=max_retries,
            failed_gate=failed_gate,
            failed_level=failed_level,
            failed_contract_ref=failed_contract_ref,
            failure_details=FailureDetails(summary=summary, errors=errors, hint=hint),
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def _current_or_default_run_id(state: ProjectState) -> str:
        if state.run_history:
            return state.run_history[-1].run_id
        return "n/a"

    def _write_input_report_if_run_exists(self, state: ProjectState, gate_report: dict[str, Any]) -> None:
        current_run = self._state_manager.current_run(state)
        if current_run is None:
            return
        self._state_manager.write_gate_report(current_run.run_id, GateId.INPUT_GATE.value, gate_report)


def path_matches_any_pattern(path: str, patterns: list[str]) -> bool:
    normalized_path = path.lstrip("./")
    for pattern in patterns:
        normalized_pattern = pattern.lstrip("./")
        if fnmatch(normalized_path, normalized_pattern):
            return True
        if PurePath(normalized_path).match(normalized_pattern):
            return True
        if "**" in normalized_pattern:
            flattened = normalized_pattern.replace("**", "*")
            if fnmatch(normalized_path, flattened):
                return True
            if PurePath(normalized_path).match(flattened):
                return True
    return False


def command_matches_any_prefix(command: str, prefixes: list[str]) -> bool:
    head = command.strip().split(" ")[0] if command.strip() else ""
    for prefix in prefixes:
        cleaned = prefix.strip()
        if not cleaned:
            continue
        if command == cleaned:
            return True
        if command.startswith(f"{cleaned} "):
            return True
        if command.startswith(f"{cleaned}/"):
            return True
        if head == cleaned:
            return True
    return False
