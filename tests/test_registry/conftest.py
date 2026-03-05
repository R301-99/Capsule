from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
import yaml


class PayloadFactory:
    @staticmethod
    def meta(
        contract_type: str,
        contract_id: str,
        *,
        version: str = "1.0.0",
        status: str = "active",
        dependencies: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": contract_type,
            "id": contract_id,
            "version": version,
            "status": status,
            "created_by": "role.architect",
            "created_at": "2026-03-04T00:00:00Z",
            "dependencies": dependencies or [],
            "validation": {"schema": "contracts/schemas/placeholder.json", "checks": []},
            "on_failure": {"action": "retry", "max_retries": 3, "severity": "mid"},
        }

    @classmethod
    def role(
        cls, *, contract_id: str = "role.coder_backend", version: str = "1.0.0", status: str = "active"
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta("role", contract_id, version=version, status=status),
            "spec": {
                "display_name": "Backend Coder",
                "capabilities": {"read": ["src/**"], "write": ["src/**"], "exec": ["pytest"]},
                "prohibitions": {"write": ["state/**"], "exec": ["git push"]},
                "retry_policy": {"max_retries": 3},
                "confidence_threshold": 0.7,
            },
        }

    @classmethod
    def boundary(
        cls, *, contract_id: str = "boundary.global", version: str = "1.0.0", status: str = "active"
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta("boundary", contract_id, version=version, status=status),
            "spec": {
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
        }

    @classmethod
    def behavior(
        cls, *, contract_id: str = "behavior.user_auth", version: str = "1.0.0", status: str = "active"
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta("behavior", contract_id, version=version, status=status),
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

    @classmethod
    def interface(
        cls, *, contract_id: str = "interface.user_auth", version: str = "1.0.0", status: str = "active"
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta("interface", contract_id, version=version, status=status),
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

    @classmethod
    def task(
        cls,
        *,
        contract_id: str = "task.user_auth.login_api",
        version: str = "1.0.0",
        status: str = "active",
        dependencies: list[dict[str, str]] | None = None,
        behavior_ref_version: str = "1.x",
        interface_ref_version: str = "1.0.0",
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta(
                "task",
                contract_id,
                version=version,
                status=status,
                dependencies=dependencies
                or [
                    {"id": "behavior.user_auth", "version": "1.x"},
                    {"id": "interface.user_auth", "version": "1.0.0"},
                ],
            ),
            "spec": {
                "assigned_to": "role.coder_backend",
                "scope": {"include": ["src/backend/**"], "exclude": [], "create_allowed": ["src/backend/"]},
                "acceptance": {
                    "behavior_ref": {"id": "behavior.user_auth", "version": behavior_ref_version},
                    "interface_refs": [{"id": "interface.user_auth", "version": interface_ref_version}],
                    "max_new_files": 5,
                },
                "token_budget": 8000,
            },
        }


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def payload_factory() -> PayloadFactory:
    return PayloadFactory()


@pytest.fixture
def write_yaml(project_root: Path) -> Callable[[str, Any], Path]:
    def _write(relative_path: str, payload: Any) -> Path:
        path = project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def populate_valid_contracts(
    write_yaml: Callable[[str, Any], Path], payload_factory: PayloadFactory
) -> Callable[[], dict[str, Path]]:
    def _populate() -> dict[str, Path]:
        return {
            "role": write_yaml("roles/coder_backend.yaml", payload_factory.role()),
            "boundary": write_yaml("contracts/boundaries/global.yaml", payload_factory.boundary()),
            "behavior": write_yaml("contracts/instances/user_auth/behavior.yaml", payload_factory.behavior()),
            "interface": write_yaml("contracts/instances/user_auth/interface.yaml", payload_factory.interface()),
            "task": write_yaml("contracts/instances/user_auth/task.yaml", payload_factory.task()),
        }

    return _populate

