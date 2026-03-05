from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from core.registry import Registry
from core.state_manager import StateManager
from core.validator import Validator


class PayloadFactory:
    @staticmethod
    def meta(
        contract_type: str,
        contract_id: str,
        *,
        version: str = "1.0.0",
        status: str = "active",
        created_by: str = "role.architect",
        dependencies: list[dict[str, str]] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        return {
            "type": contract_type,
            "id": contract_id,
            "version": version,
            "status": status,
            "created_by": created_by,
            "created_at": "2026-03-04T00:00:00Z",
            "dependencies": dependencies or [],
            "validation": {"schema": "contracts/schemas/placeholder.json", "checks": []},
            "on_failure": {"action": "retry", "max_retries": max_retries, "severity": "mid"},
        }

    @classmethod
    def role(
        cls,
        *,
        retry_max: int = 3,
        write_capabilities: list[str] | None = None,
        write_prohibitions: list[str] | None = None,
        exec_capabilities: list[str] | None = None,
        exec_prohibitions: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta("role", "role.coder_backend"),
            "spec": {
                "display_name": "Backend Coder",
                "capabilities": {
                    "read": ["src/**"],
                    "write": write_capabilities or ["src/**", "contracts/**"],
                    "exec": exec_capabilities or ["pytest", "python"],
                },
                "prohibitions": {
                    "write": write_prohibitions or ["state/**", "contracts/schemas/**"],
                    "exec": exec_prohibitions or ["git push"],
                },
                "retry_policy": {"max_retries": retry_max},
                "confidence_threshold": 0.7,
            },
        }

    @classmethod
    def boundary(cls, *, sacred_files: list[str] | None = None) -> dict[str, Any]:
        return {
            "meta": cls.meta("boundary", "boundary.global"),
            "spec": {
                "sacred_files": sacred_files or ["contracts/schemas/**", "state/**"],
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
    def behavior(cls, *, created_by: str = "role.qa") -> dict[str, Any]:
        return {
            "meta": cls.meta(
                "behavior",
                "behavior.user_auth",
                created_by=created_by,
            ),
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
    def interface(cls) -> dict[str, Any]:
        return {
            "meta": cls.meta("interface", "interface.user_auth"),
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
        behavior_ref: dict[str, str] | None = None,
        interface_refs: list[dict[str, str]] | None = None,
        scope_include: list[str] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        return {
            "meta": cls.meta(
                "task",
                "task.user_auth.login_api",
                dependencies=[
                    {"id": "behavior.user_auth", "version": "1.x"},
                    {"id": "interface.user_auth", "version": "1.0.0"},
                ],
                max_retries=max_retries,
            ),
            "spec": {
                "assigned_to": "role.coder_backend",
                "scope": {
                    "include": scope_include or ["src/backend/**"],
                    "exclude": [],
                    "create_allowed": ["src/backend/"],
                },
                "acceptance": {
                    "behavior_ref": behavior_ref or {"id": "behavior.user_auth", "version": "1.x"},
                    "interface_refs": interface_refs or [{"id": "interface.user_auth", "version": "1.0.0"}],
                    "max_new_files": 5,
                },
                "token_budget": 8000,
            },
        }


@pytest.fixture
def payload_factory() -> PayloadFactory:
    return PayloadFactory()


@pytest.fixture
def build_env(
    tmp_path: Path, payload_factory: PayloadFactory
) -> Callable[..., dict[str, Any]]:
    counter = {"value": 0}

    def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _build_env(
        *,
        include_role: bool = True,
        include_boundary: bool = True,
        include_behavior: bool = True,
        include_interface: bool = True,
        include_task: bool = True,
        role_payload: dict[str, Any] | None = None,
        boundary_payload: dict[str, Any] | None = None,
        behavior_payload: dict[str, Any] | None = None,
        interface_payload: dict[str, Any] | None = None,
        task_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        counter["value"] += 1
        project_root = tmp_path / f"project_{counter['value']}"

        if include_role:
            _write_yaml(project_root / "roles" / "coder_backend.yaml", role_payload or payload_factory.role())
        if include_boundary:
            _write_yaml(
                project_root / "contracts" / "boundaries" / "global.yaml",
                boundary_payload or payload_factory.boundary(),
            )
        if include_behavior:
            _write_yaml(
                project_root / "contracts" / "instances" / "user_auth" / "behavior.yaml",
                behavior_payload or payload_factory.behavior(),
            )
        if include_interface:
            _write_yaml(
                project_root / "contracts" / "instances" / "user_auth" / "interface.yaml",
                interface_payload or payload_factory.interface(),
            )
        if include_task:
            _write_yaml(
                project_root / "contracts" / "instances" / "user_auth" / "task.yaml",
                task_payload or payload_factory.task(),
            )

        registry = Registry.build(project_root)
        state_manager = StateManager(project_root / "state")
        state = state_manager.init_project("test-proj")
        validator = Validator(registry, state_manager)

        return {
            "project_root": project_root,
            "registry": registry,
            "state_manager": state_manager,
            "state": state,
            "validator": validator,
        }

    return _build_env

