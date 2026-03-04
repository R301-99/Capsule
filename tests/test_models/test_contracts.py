import pytest
from pydantic import ValidationError

from core.models.behavior import BehaviorContract
from core.models.boundary import BoundaryContract
from core.models.interface import InterfaceContract
from core.models.role import RoleContract
from core.models.task import TaskContract
from core.models.enums import ContractStatus, ContractType, CreatedBy


def meta_payload(contract_type: str, contract_id: str) -> dict:
    return {
        "type": contract_type,
        "id": contract_id,
        "version": "1.0.0",
        "status": ContractStatus.ACTIVE,
        "created_by": CreatedBy.SYSTEM,
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": {"schema": "contracts/schemas/x.json", "checks": []},
        "on_failure": {"action": "retry", "max_retries": 3, "severity": "mid"},
    }


def test_role_contract_valid() -> None:
    RoleContract(
        meta=meta_payload("role", "role.dev.backend"),
        spec={
            "display_name": "Backend Coder",
            "capabilities": {"read": ["src/**"], "write": ["src/**"], "exec": ["pytest"]},
            "prohibitions": {"write": ["state/**"], "exec": ["git push"]},
            "retry_policy": {"max_retries": 3},
            "confidence_threshold": 0.7,
        },
    )


def test_task_contract_valid() -> None:
    TaskContract(
        meta=meta_payload("task", "task.user_auth.login_api"),
        spec={
            "assigned_to": "role.coder_backend",
            "scope": {"include": ["src/backend/auth/**"], "exclude": [], "create_allowed": []},
            "acceptance": {
                "behavior_ref": {"id": "behavior.user_auth", "version": "1.x"},
                "interface_refs": [{"id": "interface.user_auth", "version": "1.x"}],
                "max_new_files": 5,
            },
            "token_budget": 8000,
        },
    )


def test_interface_behavior_boundary_contracts_valid() -> None:
    InterfaceContract(
        meta=meta_payload("interface", "interface.user_auth"),
        spec={
            "endpoints": [
                {
                    "id": "login",
                    "path": "/api/auth/login",
                    "method": "POST",
                    "request": {"schema": {"type": "object"}},
                    "response": {"success": {"status": 200, "schema": {"type": "object"}}},
                }
            ],
            "binding": {"producer": "role.coder_backend", "consumers": ["role.coder_frontend"]},
            "change_policy": {"requires_approval": ["role.architect"], "on_change": "suspend_dependent_tasks"},
        },
    )

    BehaviorContract(
        meta=meta_payload("behavior", "behavior.user_auth"),
        spec={
            "test_suite": {
                "runner": "pytest",
                "entry": "tests/backend/test_user_auth.py",
                "command": "pytest -q tests/backend/test_user_auth.py",
            },
            "mandatory_cases": [{"id": "TC001", "description": "login", "must_pass": True}],
            "coverage": {"minimum_percent": 80},
        },
    )

    BoundaryContract(
        meta=meta_payload("boundary", "boundary.global"),
        spec={
            "sacred_files": ["state/**"],
            "rules": [
                {
                    "id": "no_sacred_write",
                    "check_method": "git_diff_scan",
                    "violation_action": "immediate_halt",
                }
            ],
            "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
        },
    )


def test_type_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        RoleContract(
            meta=meta_payload(ContractType.TASK, "role.dev.backend"),
            spec={
                "display_name": "Backend Coder",
                "capabilities": {"read": [], "write": [], "exec": []},
                "prohibitions": {"write": [], "exec": []},
                "retry_policy": {"max_retries": 3},
                "confidence_threshold": 0.5,
            },
        )


def test_boundary_sacred_files_non_empty() -> None:
    with pytest.raises(ValidationError):
        BoundaryContract(
            meta=meta_payload("boundary", "boundary.global"),
            spec={
                "sacred_files": [],
                "rules": [{"id": "x", "check_method": "git_diff_scan", "violation_action": "immediate_halt"}],
                "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
            },
        )
