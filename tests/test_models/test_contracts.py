import json
from pathlib import Path

import pytest
import yaml
from jsonschema import validate
from pydantic import ValidationError

from core.models.behavior import BehaviorContract
from core.models.boundary import BoundaryContract
from core.models.interface import InterfaceContract
from core.models.role import RoleContract
from core.models.task import TaskContract
from core.models.export_schemas import export_schemas


def _meta(contract_type: str, contract_id: str) -> dict:
    return {
        "type": contract_type,
        "id": contract_id,
        "version": "1.0.0",
        "status": "active",
        "created_by": "role.architect",
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": {"schema": "contracts/schemas/placeholder.json", "checks": []},
        "on_failure": {"action": "retry", "max_retries": 3, "severity": "mid"},
    }


def test_all_contract_models_accept_valid_payloads_and_schema_roundtrip(tmp_path: Path) -> None:
    export_schemas(tmp_path)

    role_payload = {
        "meta": _meta("role", "role.coder_backend"),
        "spec": {
            "display_name": "Backend Coder",
            "capabilities": {"read": ["src/**"], "write": ["src/**"], "exec": ["pytest"]},
            "prohibitions": {"write": ["state/**"], "exec": ["git push"]},
            "retry_policy": {"max_retries": 3},
            "confidence_threshold": 0.7,
        },
        "extensions": {},
    }
    role = RoleContract(**yaml.safe_load(yaml.safe_dump(role_payload)))

    task_payload = {
        "meta": _meta("task", "task.user_auth.login_api"),
        "spec": {
            "assigned_to": "role.coder_backend",
            "scope": {"include": ["src/backend/**"], "exclude": [], "create_allowed": ["src/backend/"]},
            "acceptance": {
                "behavior_ref": {"id": "behavior.user_auth", "version": "1.x"},
                "interface_refs": [{"id": "interface.user_auth", "version": "1.0.0"}],
                "max_new_files": 5,
            },
            "token_budget": 8000,
        },
        "extensions": {},
    }
    task = TaskContract(**task_payload)

    interface_payload = {
        "meta": _meta("interface", "interface.user_auth"),
        "spec": {
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
        "extensions": {},
    }
    interface = InterfaceContract(**interface_payload)

    behavior_payload = {
        "meta": _meta("behavior", "behavior.user_auth"),
        "spec": {
            "test_suite": {
                "runner": "pytest",
                "entry": "tests/backend/test_auth.py",
                "command": "pytest -q tests/backend/test_auth.py",
            },
            "mandatory_cases": [{"id": "TC001", "description": "works", "must_pass": True}],
            "coverage": {"minimum_percent": 80},
        },
        "extensions": {},
    }
    behavior = BehaviorContract(**behavior_payload)

    boundary_payload = {
        "meta": _meta("boundary", "boundary.global"),
        "spec": {
            "sacred_files": ["state/**"],
            "rules": [{"id": "no_sacred_write", "check_method": "git_diff_scan", "violation_action": "immediate_halt"}],
            "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
        },
        "extensions": {},
    }
    boundary = BoundaryContract(**boundary_payload)

    models = [
        (role, "role.contract.schema.json"),
        (task, "task.contract.schema.json"),
        (interface, "interface.contract.schema.json"),
        (behavior, "behavior.contract.schema.json"),
        (boundary, "boundary.contract.schema.json"),
    ]
    for model, schema_file in models:
        schema = json.loads((tmp_path / schema_file).read_text(encoding="utf-8"))
        validate(instance=model.model_dump(mode="json"), schema=schema)


def test_model_type_mismatch_rejected() -> None:
    payload = {
        "meta": _meta("task", "role.coder_backend"),
        "spec": {
            "display_name": "Backend Coder",
            "capabilities": {"read": [], "write": [], "exec": []},
            "prohibitions": {"write": [], "exec": []},
            "retry_policy": {"max_retries": 0},
            "confidence_threshold": 0.5,
        },
    }

    with pytest.raises(ValidationError):
        RoleContract(**payload)


def test_boundary_sacred_files_cannot_be_empty() -> None:
    payload = {
        "meta": _meta("boundary", "boundary.global"),
        "spec": {
            "sacred_files": [],
            "rules": [{"id": "no_sacred_write", "check_method": "git_diff_scan", "violation_action": "immediate_halt"}],
            "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
        },
    }

    with pytest.raises(ValidationError):
        BoundaryContract(**payload)


def test_task_acceptance_rejects_non_interface_ref() -> None:
    payload = {
        "meta": _meta("task", "task.user_auth.login_api"),
        "spec": {
            "assigned_to": "role.coder_backend",
            "scope": {"include": ["src/backend/**"], "exclude": [], "create_allowed": ["src/backend/"]},
            "acceptance": {
                "behavior_ref": {"id": "behavior.user_auth", "version": "1.x"},
                "interface_refs": [{"id": "task.not_interface", "version": "1.0.0"}],
                "max_new_files": 5,
            },
            "token_budget": 8000,
        },
        "extensions": {},
    }

    with pytest.raises(ValidationError):
        TaskContract(**payload)


def test_interface_binding_rejects_invalid_consumer_role() -> None:
    payload = {
        "meta": _meta("interface", "interface.user_auth"),
        "spec": {
            "endpoints": [
                {
                    "id": "login",
                    "path": "/api/auth/login",
                    "method": "POST",
                    "request": {"schema": {"type": "object"}},
                    "response": {"success": {"status": 200, "schema": {"type": "object"}}},
                }
            ],
            "binding": {"producer": "role.coder_backend", "consumers": ["coder_frontend"]},
            "change_policy": {"requires_approval": ["role.architect"], "on_change": "suspend_dependent_tasks"},
        },
        "extensions": {},
    }

    with pytest.raises(ValidationError):
        InterfaceContract(**payload)
