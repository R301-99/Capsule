from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from core.models.execution import ExecutionResult
from core.state_manager import StateManager
from core.test_runner import TestResult


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


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)

    role_backend = {
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
            "retry_policy": {"max_retries": 2},
            "confidence_threshold": 0.7,
        },
    }
    role_architect = {
        "meta": _meta("role", "role.architect"),
        "spec": {
            "display_name": "Architect",
            "capabilities": {"read": ["**"], "write": ["contracts/**"], "exec": ["python"]},
            "prohibitions": {"write": [], "exec": ["git push"]},
            "retry_policy": {"max_retries": 2},
            "confidence_threshold": 0.8,
        },
    }
    role_qa = {
        "meta": _meta("role", "role.qa"),
        "spec": {
            "display_name": "QA",
            "capabilities": {"read": ["**"], "write": ["tests/**"], "exec": ["pytest"]},
            "prohibitions": {"write": ["src/**"], "exec": ["git push"]},
            "retry_policy": {"max_retries": 2},
            "confidence_threshold": 0.8,
        },
    }
    boundary = {
        "meta": _meta("boundary", "boundary.global"),
        "spec": {
            "sacred_files": ["contracts/schemas/**", "state/**", ".env*"],
            "rules": [{"id": "no_sacred_write", "check_method": "git_diff_scan", "violation_action": "immediate_halt"}],
            "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
        },
    }
    behavior = {
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
    interface = {
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
            "binding": {"producer": "role.coder_backend", "consumers": []},
            "change_policy": {"requires_approval": ["role.architect"], "on_change": "suspend_dependent_tasks"},
        },
    }
    task = {
        "meta": _meta("task", "task.user_auth.login_api", max_retries=1),
        "spec": {
            "assigned_to": "role.coder_backend",
            "scope": {"include": ["src/backend/**"], "exclude": [], "create_allowed": ["src/backend/auth/"]},
            "acceptance": {
                "behavior_ref": {"id": "behavior.user_auth", "version": "1.0.0"},
                "interface_refs": [{"id": "interface.user_auth", "version": "1.0.0"}],
                "max_new_files": 5,
            },
            "token_budget": 8000,
        },
    }

    _write_yaml(root / "roles" / "coder_backend.contract.yaml", role_backend)
    _write_yaml(root / "roles" / "architect.contract.yaml", role_architect)
    _write_yaml(root / "roles" / "qa.contract.yaml", role_qa)
    _write_yaml(root / "contracts" / "boundaries" / "global.boundary.yaml", boundary)
    _write_yaml(root / "contracts" / "instances" / "user_auth" / "behavior.contract.yaml", behavior)
    _write_yaml(root / "contracts" / "instances" / "user_auth" / "interface.contract.yaml", interface)
    _write_yaml(root / "contracts" / "instances" / "user_auth" / "task.contract.yaml", task)

    (root / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "standard.yaml").write_text(
        yaml.safe_dump(
            {
                "workflow": {
                    "id": "workflow.standard",
                    "nodes": [{"id": "coder_backend", "role": "role.coder_backend", "action": "implement"}],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    (root / "capsule.yaml").write_text(
        "capsule:\n"
        "  project_id: test-project\n"
        "  workflow: workflows/standard.yaml\n"
        "  executor:\n"
        "    type: codex_cli\n"
        "    codex_command: codex\n"
        "    timeout_seconds: 300\n"
        "  test_runner:\n"
        "    timeout_seconds: 120\n",
        encoding="utf-8",
    )

    return root


@pytest.fixture
def initialized_project(project_root: Path) -> Path:
    sm = StateManager(project_root / "state")
    sm.init_project("test-project")
    return project_root


@pytest.fixture
def patch_cli_runtime(monkeypatch):
    import core.cli as cli

    def _apply(
        *,
        exec_results: list[ExecutionResult] | None = None,
        test_results: list[TestResult] | None = None,
    ) -> None:
        exec_queue = list(exec_results or [
            ExecutionResult(
                success=True,
                exit_code=0,
                modified_files=["src/backend/auth/login.py"],
                commands_ran=[{"cmd": "codex exec task", "exit_code": 0, "duration_ms": 30}],
                agent_output="ok",
                duration_ms=30,
            )
        ])
        test_queue = list(test_results or [
            TestResult(
                passed=True,
                exit_code=0,
                command="pytest -q tests/backend/test_user_auth.py",
                stdout="ok",
                stderr="",
                duration_ms=10,
                summary="All tests passed",
                error_details=[],
            )
        ])

        class FakeExecutor:
            def __init__(self, queue: list[ExecutionResult]):
                self._queue = queue

            def execute(self, request):
                if len(self._queue) > 1:
                    return self._queue.pop(0)
                return self._queue[0]

        class FakeTestRunner:
            def __init__(self, timeout_seconds: int = 120):
                self.timeout_seconds = timeout_seconds

            def run(self, command: str, working_dir):
                if len(test_queue) > 1:
                    return test_queue.pop(0)
                return test_queue[0]

        monkeypatch.setattr(cli, "_build_executor", lambda config: FakeExecutor(exec_queue))
        monkeypatch.setattr(cli, "TestRunner", FakeTestRunner)

    return _apply
