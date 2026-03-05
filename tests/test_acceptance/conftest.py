"""
Architect Acceptance Tests — Shared Fixtures
=============================================
DO NOT MODIFY THIS FILE. If fixtures fail, fix the implementation.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _meta(
    type_: str,
    id_: str,
    version: str = "1.0.0",
    status: str = "active",
    created_by: str = "role.architect",
    deps: list = None,
) -> dict:
    return {
        "type": type_,
        "id": id_,
        "version": version,
        "status": status,
        "created_by": created_by,
        "created_at": "2026-01-01T00:00:00Z",
        "dependencies": deps or [],
        "validation": {
            "schema": "contracts/schemas/{}.contract.schema.json".format(type_),
            "checks": [],
        },
        "on_failure": {"action": "retry", "max_retries": 3, "severity": "mid"},
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def make_evidence_dict(run_id: str = "20260101-000000-abcdef01") -> dict:
    """Build a minimal valid ExecutionEvidenceSpec dict."""
    return {
        "run_id": run_id,
        "role_id": "role.coder_backend",
        "task_ref": {"id": "task.user_auth.login_api", "version": "1.0.0"},
        "contract_snapshot": {
            "refs": [
                {"id": "task.user_auth.login_api", "version": "1.0.0"},
                {"id": "behavior.user_auth", "version": "1.0.0"},
                {"id": "interface.user_auth", "version": "1.0.0"},
            ]
        },
        "changes": {
            "modified_files": ["src/backend/auth/login.py"],
            "diff_stat": {"files": 1, "insertions": 20, "deletions": 0},
        },
        "commands": {
            "ran": [{"cmd": "codex exec task", "exit_code": 0, "duration_ms": 5000}]
        },
        "tests": {"ran": [], "summary": "pass"},
        "self_report": {"confidence": 0.8, "risks": [], "notes": "done"},
    }


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a complete mini Capsule project with all contract types."""
    root = tmp_path / "project"
    root.mkdir()

    # ── roles ──
    _write(root / "roles" / "coder_backend.contract.yaml", {"contract": {
        "meta": _meta("role", "role.coder_backend"),
        "spec": {
            "display_name": "Backend Coder",
            "capabilities": {
                "read": ["src/backend/**", "contracts/**"],
                "write": ["src/backend/**", "tests/backend/**"],
                "exec": ["pytest", "python"],
            },
            "prohibitions": {
                "write": ["contracts/schemas/**", "state/**"],
                "exec": ["git push", "rm -rf"],
            },
            "retry_policy": {"max_retries": 3},
            "confidence_threshold": 0.7,
        },
        "extensions": {},
    }})

    _write(root / "roles" / "qa.contract.yaml", {"contract": {
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
        "extensions": {},
    }})

    _write(root / "roles" / "architect.contract.yaml", {"contract": {
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
        "extensions": {},
    }})

    # ── boundary ──
    _write(root / "contracts" / "boundaries" / "global.boundary.yaml", {"contract": {
        "meta": _meta("boundary", "boundary.global"),
        "spec": {
            "sacred_files": [
                "capsule.yaml",
                "contracts/schemas/*",
                "state/*",
                ".env*",
            ],
            "rules": [{
                "id": "no_sacred_write",
                "check_method": "git_diff_scan",
                "violation_action": "immediate_halt",
            }],
            "on_violation": {
                "notify": "human",
                "log_path": "state/audit/boundary_violations.log",
            },
        },
        "extensions": {},
    }})

    # ── contract instances ──
    inst = root / "contracts" / "instances" / "user_auth"

    _write(inst / "interface.contract.yaml", {"contract": {
        "meta": _meta("interface", "interface.user_auth"),
        "spec": {
            "endpoints": [{
                "id": "login",
                "path": "/api/auth/login",
                "method": "POST",
                "request": {
                    "schema": {
                        "type": "object",
                        "required": ["email", "password"],
                        "properties": {
                            "email": {"type": "string"},
                            "password": {"type": "string"},
                        },
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
            }],
            "binding": {"producer": "role.coder_backend", "consumers": []},
            "change_policy": {
                "requires_approval": ["role.architect"],
                "on_change": "suspend_dependent_tasks",
            },
        },
        "extensions": {},
    }})

    _write(inst / "behavior.contract.yaml", {"contract": {
        "meta": _meta("behavior", "behavior.user_auth", created_by="role.qa"),
        "spec": {
            "test_suite": {
                "runner": "pytest",
                "entry": "tests/backend/test_user_auth.py",
                "command": "pytest -q tests/backend/test_user_auth.py",
            },
            "mandatory_cases": [
                {"id": "TC001", "description": "Login returns JWT", "must_pass": True},
            ],
        },
        "extensions": {},
    }})

    _write(inst / "task.contract.yaml", {"contract": {
        "meta": _meta("task", "task.user_auth.login_api", deps=[
            {"id": "interface.user_auth", "version": "1.0.0"},
            {"id": "behavior.user_auth", "version": "1.0.0"},
        ]),
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
        "extensions": {},
    }})

    # ── required dirs ──
    (root / "contracts" / "schemas").mkdir(parents=True, exist_ok=True)

    # ── git init (for Phase 5 git_utils compatibility) ──
    env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t.com",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com"}
    subprocess.run(["git", "init"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-m", "init"], cwd=root, capture_output=True, env=env)

    return root
