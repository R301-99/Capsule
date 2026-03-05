from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest
import yaml

from core.executor.port import ExecutorPort
from core.models.base import ContractRef
from core.models.execution import ExecutionResult
from core.orchestrator import Orchestrator
from core.registry import Registry
from core.state_manager import StateManager
from core.test_runner import TestResult, TestRunner
from core.validator import Validator


def _meta(
    contract_type: str,
    contract_id: str,
    *,
    version: str = "1.0.0",
    status: str = "active",
    created_by: str = "role.architect",
    max_retries: int = 1,
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
        "on_failure": {"action": "retry", "max_retries": max_retries, "severity": "mid"},
    }


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _execution_result(
    *,
    success: bool = True,
    modified_files: list[str] | None = None,
    commands_ran: list[dict[str, Any]] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        success=success,
        exit_code=0 if success else 1,
        modified_files=modified_files or ["src/backend/auth/login.py"],
        commands_ran=commands_ran
        or [{"cmd": "codex exec task", "exit_code": 0 if success else 1, "duration_ms": 100}],
        agent_output="Done" if success else "Failed",
        error_message=None if success else "execution failed",
        duration_ms=100,
    )


@pytest.fixture
def build_orchestrator(tmp_path: Path) -> Callable[..., dict[str, Any]]:
    counter = {"value": 0}

    def _build(
        *,
        task_max_retries: int = 1,
        role_retry_max: int = 3,
        executor: ExecutorPort | None = None,
        test_runner: TestRunner | None = None,
    ) -> dict[str, Any]:
        counter["value"] += 1
        project_root = tmp_path / f"project_{counter['value']}"

        role_backend_payload = {
            "meta": _meta("role", "role.coder_backend"),
            "spec": {
                "display_name": "Backend Coder",
                "capabilities": {
                    "read": ["src/**", "contracts/**"],
                    "write": ["src/backend/**", "tests/backend/**"],
                    "exec": ["pytest", "python"],
                },
                "prohibitions": {
                    "write": ["contracts/schemas/**", "state/**"],
                    "exec": ["git push", "rm -rf"],
                },
                "retry_policy": {"max_retries": role_retry_max},
                "confidence_threshold": 0.7,
            },
        }
        role_architect_payload = {
            "meta": _meta("role", "role.architect"),
            "spec": {
                "display_name": "Architect",
                "capabilities": {
                    "read": ["**"],
                    "write": ["contracts/**", "roles/**"],
                    "exec": ["python"],
                },
                "prohibitions": {"write": [], "exec": ["git push"]},
                "retry_policy": {"max_retries": 2},
                "confidence_threshold": 0.8,
            },
        }
        role_qa_payload = {
            "meta": _meta("role", "role.qa"),
            "spec": {
                "display_name": "QA",
                "capabilities": {
                    "read": ["**"],
                    "write": ["tests/**"],
                    "exec": ["pytest"],
                },
                "prohibitions": {"write": ["src/**"], "exec": ["git push"]},
                "retry_policy": {"max_retries": 2},
                "confidence_threshold": 0.8,
            },
        }
        boundary_payload = {
            "meta": _meta("boundary", "boundary.global"),
            "spec": {
                "sacred_files": ["contracts/schemas/**", "state/**", ".env*"],
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
        behavior_payload = {
            "meta": _meta("behavior", "behavior.user_auth", created_by="role.qa"),
            "spec": {
                "test_suite": {
                    "runner": "pytest",
                    "entry": "tests/backend/test_user_auth.py",
                    "command": "pytest -q tests/backend/test_user_auth.py",
                },
                "mandatory_cases": [{"id": "TC001", "description": "Login returns JWT", "must_pass": True}],
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
                        "request": {
                            "schema": {
                                "type": "object",
                                "required": ["email", "password"],
                                "properties": {"email": {"type": "string"}, "password": {"type": "string"}},
                            }
                        },
                        "response": {
                            "success": {
                                "status": 200,
                                "schema": {
                                    "type": "object",
                                    "required": ["token"],
                                    "properties": {"token": {"type": "string"}},
                                },
                            }
                        },
                    }
                ],
                "binding": {"producer": "role.coder_backend", "consumers": []},
                "change_policy": {
                    "requires_approval": ["role.architect"],
                    "on_change": "suspend_dependent_tasks",
                },
            },
        }
        task_payload = {
            "meta": _meta("task", "task.user_auth.login_api", max_retries=task_max_retries),
            "spec": {
                "assigned_to": "role.coder_backend",
                "scope": {
                    "include": ["src/backend/**"],
                    "exclude": [],
                    "create_allowed": ["src/backend/auth/"],
                },
                "acceptance": {
                    "behavior_ref": {"id": "behavior.user_auth", "version": "1.0.0"},
                    "interface_refs": [{"id": "interface.user_auth", "version": "1.0.0"}],
                    "max_new_files": 5,
                },
                "token_budget": 8000,
            },
        }

        _write_yaml(project_root / "roles" / "coder_backend.contract.yaml", role_backend_payload)
        _write_yaml(project_root / "roles" / "architect.contract.yaml", role_architect_payload)
        _write_yaml(project_root / "roles" / "qa.contract.yaml", role_qa_payload)
        _write_yaml(project_root / "contracts" / "boundaries" / "global.boundary.yaml", boundary_payload)
        _write_yaml(project_root / "contracts" / "instances" / "user_auth" / "behavior.contract.yaml", behavior_payload)
        _write_yaml(project_root / "contracts" / "instances" / "user_auth" / "interface.contract.yaml", interface_payload)
        _write_yaml(project_root / "contracts" / "instances" / "user_auth" / "task.contract.yaml", task_payload)

        registry = Registry.build(project_root)
        state_manager = StateManager(project_root / "state")
        state = state_manager.init_project("test-project")
        state_manager.save(state)
        validator = Validator(registry, state_manager)

        mock_executor: ExecutorPort
        if executor is None:
            mock_executor = MagicMock(spec=ExecutorPort)
            mock_executor.execute.return_value = _execution_result(success=True)
        else:
            mock_executor = executor

        runner: TestRunner
        if test_runner is None:
            runner = MagicMock(spec=TestRunner)
            runner.run.return_value = TestResult(
                passed=True,
                exit_code=0,
                command="pytest -q tests/backend/test_user_auth.py",
                stdout="ok",
                stderr="",
                duration_ms=100,
                summary="All tests passed",
                error_details=[],
            )
        else:
            runner = test_runner

        orchestrator = Orchestrator(
            registry=registry,
            state_manager=state_manager,
            validator=validator,
            executor=mock_executor,
            test_runner=runner,
            project_root=project_root,
        )

        return {
            "project_root": project_root,
            "registry": registry,
            "state_manager": state_manager,
            "validator": validator,
            "orchestrator": orchestrator,
            "executor": mock_executor,
            "test_runner": runner,
            "task_ref": ContractRef(id="task.user_auth.login_api", version="1.0.0"),
            "execution_result": _execution_result,
        }

    return _build
