from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from core.registry import Registry
from core.state_manager import StateManager
from core.validator import Validator


def _meta(
    contract_type: str,
    contract_id: str,
    *,
    version: str = "1.0.0",
    status: str = "active",
    created_by: str = "role.architect",
) -> dict[str, Any]:
    return {
        "type": contract_type,
        "id": contract_id,
        "version": version,
        "status": status,
        "created_by": created_by,
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": {"schema": "contracts/schemas/placeholder.json", "checks": []},
        "on_failure": {"action": "retry", "max_retries": 3, "severity": "mid"},
    }


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.fixture
def micro_project(tmp_path: Path) -> dict[str, Any]:
    project_root = tmp_path / "capsule_project"

    role_payload = {
        "meta": _meta("role", "role.coder_backend"),
        "spec": {
            "display_name": "Backend Coder",
            "capabilities": {"read": ["src/**"], "write": ["src/**", "contracts/**"], "exec": ["pytest", "python"]},
            "prohibitions": {"write": ["state/**", "contracts/schemas/**"], "exec": ["git push"]},
            "retry_policy": {"max_retries": 3},
            "confidence_threshold": 0.7,
        },
    }
    boundary_payload = {
        "meta": _meta("boundary", "boundary.global"),
        "spec": {
            "sacred_files": ["contracts/schemas/**", "state/**"],
            "rules": [{"id": "no_sacred_write", "check_method": "git_diff_scan", "violation_action": "immediate_halt"}],
            "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
        },
    }
    behavior_payload = {
        "meta": _meta("behavior", "behavior.user_auth", created_by="role.qa"),
        "spec": {
            "test_suite": {
                "runner": "pytest",
                "entry": "tests/backend/test_auth.py",
                "command": "pytest -q tests/backend/test_auth.py",
            },
            "mandatory_cases": [{"id": "TC001", "description": "works", "must_pass": True}],
            "coverage": {"minimum_percent": 80},
        },
    }
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
    }
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
    }

    _write_yaml(project_root / "roles" / "coder_backend.yaml", role_payload)
    _write_yaml(project_root / "contracts" / "boundaries" / "global.yaml", boundary_payload)
    _write_yaml(project_root / "contracts" / "instances" / "user_auth" / "behavior.yaml", behavior_payload)
    _write_yaml(project_root / "contracts" / "instances" / "user_auth" / "interface.yaml", interface_payload)
    _write_yaml(project_root / "contracts" / "instances" / "user_auth" / "task.yaml", task_payload)

    registry = Registry.build(project_root)
    state_manager = StateManager(project_root / "state")
    state = state_manager.init_project("integration-proj")
    validator = Validator(registry, state_manager)

    return {
        "project_root": project_root,
        "registry": registry,
        "state_manager": state_manager,
        "state": state,
        "validator": validator,
    }

