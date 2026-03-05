from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models.config import CapsuleConfig
from .models.enums import ContractStatus, ContractType
from .models.workflow import WorkflowDef
from .registry import Registry, ResolutionError
from .state_manager import StateLoadError, StateManager


@dataclass(frozen=True)
class ValidationIssue:
    level: str  # error | warning
    category: str  # structure | contract | workflow | state
    message: str
    fix_hint: str


def validate_project(root: Path) -> list[ValidationIssue]:
    project_root = Path(root)
    issues: list[ValidationIssue] = []

    config: CapsuleConfig | None = None
    config_path = project_root / "capsule.yaml"
    if not config_path.exists():
        issues.append(
            ValidationIssue(
                level="error",
                category="structure",
                message=f"capsule.yaml not found: {config_path}",
                fix_hint="Run 'capsule init'",
            )
        )
    else:
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            payload = raw.get("capsule", raw) if isinstance(raw, dict) else None
            if not isinstance(payload, dict):
                raise ValueError("capsule.yaml root must be a mapping")
            config = CapsuleConfig(**payload)
        except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="structure",
                    message=f"capsule.yaml is invalid: {exc}",
                    fix_hint="Check capsule.yaml format",
                )
            )

    _validate_structure(project_root, issues)

    registry: Registry | None = None
    try:
        registry = Registry.build(project_root)
    except (FileNotFoundError, NotADirectoryError) as exc:
        issues.append(
            ValidationIssue(
                level="error",
                category="contract",
                message=f"Registry build failed: {exc}",
                fix_hint="Ensure project root exists and has contracts directories",
            )
        )

    if registry is not None:
        _validate_contracts(registry, issues)

    if config is not None and registry is not None:
        _validate_workflow(project_root, config, registry, issues)

    _validate_state(project_root, registry, issues)
    return issues


def _validate_structure(project_root: Path, issues: list[ValidationIssue]) -> None:
    roles_dir = project_root / "roles"
    if not roles_dir.exists() or not roles_dir.is_dir() or not any(roles_dir.iterdir()):
        issues.append(
            ValidationIssue(
                level="error",
                category="structure",
                message="roles/ directory missing or empty",
                fix_hint="Run 'capsule init' or add role contracts",
            )
        )

    workflows_dir = project_root / "workflows"
    if not workflows_dir.exists() or not workflows_dir.is_dir():
        issues.append(
            ValidationIssue(
                level="error",
                category="structure",
                message="workflows/ directory is missing",
                fix_hint="Run 'capsule init'",
            )
        )

    boundaries_dir = project_root / "contracts" / "boundaries"
    if not boundaries_dir.exists() or not boundaries_dir.is_dir():
        issues.append(
            ValidationIssue(
                level="error",
                category="structure",
                message="contracts/boundaries/ directory is missing",
                fix_hint="Run 'capsule init'",
            )
        )

    schemas_dir = project_root / "contracts" / "schemas"
    if not schemas_dir.exists() or not schemas_dir.is_dir() or not any(schemas_dir.iterdir()):
        issues.append(
            ValidationIssue(
                level="warning",
                category="structure",
                message="contracts/schemas/ directory missing or empty",
                fix_hint="Run 'capsule init' to generate schemas",
            )
        )

    state_dir = project_root / "state"
    if not state_dir.exists() or not state_dir.is_dir():
        issues.append(
            ValidationIssue(
                level="error",
                category="structure",
                message="state/ directory is missing",
                fix_hint="Run 'capsule init'",
            )
        )

    state_file = state_dir / "PROJECT_STATE.json"
    if not state_file.exists():
        issues.append(
            ValidationIssue(
                level="error",
                category="structure",
                message="state/PROJECT_STATE.json is missing",
                fix_hint="Run 'capsule init'",
            )
        )


def _validate_contracts(registry: Registry, issues: list[ValidationIssue]) -> None:
    for load_error in registry.load_errors:
        issues.append(
            ValidationIssue(
                level="error",
                category="contract",
                message=f"Registry load error: {load_error.file_path} - {load_error.message}",
                fix_hint=f"Fix contract YAML: {load_error.error_type}",
            )
        )

    boundaries = registry.list_by_type(ContractType.BOUNDARY)
    active_boundaries = [contract for contract in boundaries if contract.meta.status == ContractStatus.ACTIVE]
    if not active_boundaries:
        issues.append(
            ValidationIssue(
                level="error",
                category="contract",
                message="No active boundary contract found",
                fix_hint="Add a boundary contract to contracts/boundaries/",
            )
        )

    if not registry.is_boundary_intact():
        for boundary_error in registry.boundary_load_errors:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="contract",
                    message=f"Boundary contract failed to load: {boundary_error.file_path} - {boundary_error.message}",
                    fix_hint="Fix boundary contract file and re-run validation",
                )
            )


def _validate_workflow(
    project_root: Path,
    config: CapsuleConfig,
    registry: Registry,
    issues: list[ValidationIssue],
) -> None:
    workflow_path = project_root / config.workflow
    if not workflow_path.exists():
        issues.append(
            ValidationIssue(
                level="error",
                category="workflow",
                message=f"Workflow file not found: {workflow_path}",
                fix_hint="Check capsule.yaml workflow path",
            )
        )
        return

    workflow: WorkflowDef | None = None
    try:
        raw = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        payload = raw.get("workflow", raw) if isinstance(raw, dict) else None
        if not isinstance(payload, dict):
            raise ValueError("workflow root must be a mapping")
        workflow = WorkflowDef(**payload)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        issues.append(
            ValidationIssue(
                level="error",
                category="workflow",
                message=f"Workflow parse failed: {exc}",
                fix_hint="Fix workflow YAML",
            )
        )
        return

    for node in workflow.nodes:
        if registry.get_latest_active(node.role) is None:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="workflow",
                    message=f"Workflow node '{node.id}' references missing role '{node.role}'",
                    fix_hint=f"Add role contract for '{node.role}'",
                )
            )


def _validate_state(project_root: Path, registry: Registry | None, issues: list[ValidationIssue]) -> None:
    sm = StateManager(project_root / "state")
    try:
        state = sm.load()
    except StateLoadError as exc:
        issues.append(
            ValidationIssue(
                level="error",
                category="state",
                message=f"PROJECT_STATE.json is invalid: {exc}",
                fix_hint="State file corrupted. Restore from checkpoint or re-init",
            )
        )
        return

    if state.current_task_ref is not None and registry is not None:
        try:
            registry.resolve(state.current_task_ref)
        except ResolutionError:
            issues.append(
                ValidationIssue(
                    level="warning",
                    category="state",
                    message=(
                        "current_task_ref does not resolve: "
                        f"{state.current_task_ref.id}@{state.current_task_ref.version}"
                    ),
                    fix_hint="Task contract may have been removed",
                )
            )
