from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .models.export_schemas import MODEL_TO_FILE, export_schemas


@dataclass(frozen=True)
class ScaffoldReport:
    created: list[str]
    skipped: list[str]
    errors: list[str]


def scaffold_project(root: Path, project_id: str, tech_stack: str = "python") -> ScaffoldReport:
    """
    Create a complete Capsule project skeleton.

    Idempotent behavior:
    - existing files are skipped
    - missing files are created
    """
    del tech_stack  # reserved for future template branching
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    now = _iso_now()

    def write_text_if_missing(path: Path, content: str) -> None:
        if path.exists():
            skipped.append(_rel(root, path))
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(_rel(root, path))
        except OSError as exc:
            errors.append(f"{_rel(root, path)}: {exc}")

    def write_yaml_if_missing(path: Path, payload: dict[str, Any]) -> None:
        if path.exists():
            skipped.append(_rel(root, path))
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            created.append(_rel(root, path))
        except OSError as exc:
            errors.append(f"{_rel(root, path)}: {exc}")

    write_text_if_missing(root / "capsule.yaml", _capsule_yaml(project_id))
    write_text_if_missing(root / ".gitignore", _gitignore())
    write_text_if_missing(root / "CAPSULE.md", _capsule_doc(project_id))

    write_yaml_if_missing(root / "roles" / "architect.contract.yaml", _architect_role(now))
    write_yaml_if_missing(root / "roles" / "qa.contract.yaml", _qa_role(now))
    write_yaml_if_missing(root / "roles" / "coder_backend.contract.yaml", _coder_role(now))

    write_yaml_if_missing(root / "workflows" / "standard.yaml", _standard_workflow())
    write_yaml_if_missing(root / "contracts" / "boundaries" / "global.boundary.yaml", _global_boundary(now))
    write_text_if_missing(root / "contracts" / "instances" / ".gitkeep", "")

    write_text_if_missing(root / "prompts" / "architect.md", _architect_prompt())
    write_text_if_missing(root / "prompts" / "qa.md", _qa_prompt())
    write_text_if_missing(root / "prompts" / "coder.md", _coder_prompt())

    schema_dir = root / "contracts" / "schemas"
    required_schema_files = sorted(set(MODEL_TO_FILE.values()))
    missing_schema_files = [name for name in required_schema_files if not (schema_dir / name).exists()]
    for name in required_schema_files:
        schema_path = schema_dir / name
        if schema_path.exists():
            skipped.append(_rel(root, schema_path))
    if missing_schema_files:
        try:
            export_schemas(schema_dir=schema_dir)
            for name in missing_schema_files:
                created.append(_rel(root, schema_dir / name))
        except Exception as exc:  # pragma: no cover - defensive
            for name in missing_schema_files:
                errors.append(f"{_rel(root, schema_dir / name)}: {exc}")

    return ScaffoldReport(created=created, skipped=skipped, errors=errors)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _capsule_yaml(project_id: str) -> str:
    return (
        "capsule:\n"
        f"  project_id: \"{project_id}\"\n"
        "  workflow: \"workflows/standard.yaml\"\n"
        "  executor:\n"
        "    type: \"codex_cli\"\n"
        "    codex_command: \"codex\"\n"
        "    timeout_seconds: 300\n"
        "  test_runner:\n"
        "    timeout_seconds: 120\n"
        "  global_conventions: {}\n"
    )


def _gitignore() -> str:
    return (
        "# Capsule runtime (evidence, checkpoints, audit logs)\n"
        "state/runs/\n"
        "state/checkpoints/\n"
        "state/audit/\n"
        "\n"
        "# Keep PROJECT_STATE.json tracked\n"
        "!state/PROJECT_STATE.json\n"
        "\n"
        "# Python\n"
        "__pycache__/\n"
        "*.pyc\n"
        ".pytest_cache/\n"
        "\n"
        "# Environment\n"
        ".env\n"
        ".env.*\n"
    )


def _capsule_doc(project_id: str) -> str:
    return (
        f"# {project_id}\n\n"
        "This project is managed by Capsule.\n\n"
        "## Quick Start\n\n"
        "```bash\n"
        "# Initialize (already done)\n"
        "capsule init\n\n"
        "# Add a task contract, then run\n"
        "capsule run --task \"task.<module>.<name>@1.0.0\"\n\n"
        "# Review pending items\n"
        "capsule review\n\n"
        "# Make a decision\n"
        "capsule decide --item <ITEM_ID> --option approve\n\n"
        "# Resume after decision\n"
        "capsule resume\n"
        "```\n"
    )


def _meta(contract_type: str, contract_id: str, now: str, action: str, retries: int, severity: str) -> dict[str, Any]:
    return {
        "type": contract_type,
        "id": contract_id,
        "version": "1.0.0",
        "status": "active",
        "created_by": "human",
        "created_at": now,
        "dependencies": [],
        "validation": {"schema": f"contracts/schemas/{contract_type}.contract.schema.json", "checks": []},
        "on_failure": {"action": action, "max_retries": retries, "severity": severity},
    }


def _architect_role(now: str) -> dict[str, Any]:
    return {
        "contract": {
            "meta": _meta("role", "role.architect", now, action="human_escalation", retries=2, severity="high"),
            "spec": {
                "display_name": "Architect",
                "capabilities": {"read": ["**"], "write": ["contracts/**", "roles/**", "workflows/**"], "exec": ["python"]},
                "prohibitions": {"write": ["state/**", ".env*"], "exec": ["git push", "rm -rf"]},
                "retry_policy": {"max_retries": 2},
                "confidence_threshold": 0.8,
            },
            "extensions": {},
        }
    }


def _qa_role(now: str) -> dict[str, Any]:
    return {
        "contract": {
            "meta": _meta("role", "role.qa", now, action="retry", retries=2, severity="mid"),
            "spec": {
                "display_name": "QA",
                "capabilities": {
                    "read": ["**"],
                    "write": ["tests/**", "contracts/instances/**/behavior.contract.yaml"],
                    "exec": ["pytest", "python"],
                },
                "prohibitions": {"write": ["src/**", "state/**", ".env*"], "exec": ["git push", "rm -rf"]},
                "retry_policy": {"max_retries": 2},
                "confidence_threshold": 0.8,
            },
            "extensions": {},
        }
    }


def _coder_role(now: str) -> dict[str, Any]:
    return {
        "contract": {
            "meta": _meta("role", "role.coder_backend", now, action="retry", retries=3, severity="mid"),
            "spec": {
                "display_name": "Backend Coder",
                "capabilities": {
                    "read": ["src/backend/**", "contracts/**", "tests/backend/**"],
                    "write": ["src/backend/**", "tests/backend/**"],
                    "exec": ["pytest", "python", "pip"],
                },
                "prohibitions": {
                    "write": ["contracts/schemas/**", "state/**", ".env*", "src/frontend/**"],
                    "exec": ["git push", "git reset", "rm -rf"],
                },
                "retry_policy": {"max_retries": 3},
                "confidence_threshold": 0.7,
            },
            "extensions": {},
        }
    }


def _standard_workflow() -> dict[str, Any]:
    return {
        "workflow": {
            "id": "workflow.standard",
            "nodes": [
                {"id": "architect", "role": "role.architect", "action": "produce_contracts", "human_review": True},
                {"id": "qa", "role": "role.qa", "action": "produce_behavior"},
                {"id": "coder_backend", "role": "role.coder_backend", "action": "implement"},
                {"id": "architect_review", "role": "role.architect", "action": "review", "human_review": True},
            ],
        }
    }


def _global_boundary(now: str) -> dict[str, Any]:
    return {
        "contract": {
            "meta": _meta("boundary", "boundary.global", now, action="halt", retries=0, severity="high"),
            "spec": {
                "sacred_files": [
                    "capsule.yaml",
                    "contracts/schemas/*",
                    "contracts/boundaries/*",
                    "state/*",
                    ".env*",
                ],
                "rules": [
                    {"id": "no_sacred_write", "check_method": "git_diff_scan", "violation_action": "immediate_halt"},
                    {"id": "no_forbidden_exec", "check_method": "command_audit", "violation_action": "immediate_halt"},
                ],
                "on_violation": {"notify": "human", "log_path": "state/audit/boundary_violations.log"},
            },
            "extensions": {},
        }
    }


def _architect_prompt() -> str:
    return (
        "# Architect Agent\n\n"
        "You are the Architect of this project.\n\n"
        "## Your Responsibilities\n"
        "- Analyze requirements and produce technical designs\n"
        "- Create and maintain contract files (task, interface, behavior)\n"
        "- Review implementation results for architectural compliance\n\n"
        "## Constraints\n"
        "- You may only modify files under: contracts/, roles/, workflows/\n"
        "- You must produce valid YAML contract files that pass schema validation\n"
        "- Every design decision must be traceable to a requirement\n\n"
        "## Output Format\n"
        "Produce contract YAML files. Do not write implementation code.\n"
    )


def _qa_prompt() -> str:
    return (
        "# QA Agent\n\n"
        "You are the QA Engineer of this project.\n\n"
        "## Your Responsibilities\n"
        "- Design test strategies based on interface contracts\n"
        "- Create behavior contracts with test suites and mandatory cases\n"
        "- Define acceptance criteria\n\n"
        "## Constraints\n"
        "- You may only modify files under: tests/, contracts/instances/**/behavior.contract.yaml\n"
        "- You must NOT write implementation code\n"
        "- Test commands must be executable (e.g., \"pytest -q tests/...\")\n\n"
        "## Output Format\n"
        "Produce behavior.contract.yaml files with complete test_suite definitions.\n"
    )


def _coder_prompt() -> str:
    return (
        "# Coder Agent\n\n"
        "You are a Coder on this project.\n\n"
        "## Your Responsibilities\n"
        "- Implement code strictly according to task, interface, and behavior contracts\n"
        "- Ensure all tests in the behavior contract pass\n"
        "- Stay within your authorized file scope\n\n"
        "## Constraints\n"
        "- You may ONLY modify files listed in task.spec.scope.include\n"
        "- You must NOT modify any file in task.spec.scope.exclude\n"
        "- You must NOT touch any file listed in boundary.sacred_files\n"
        "- You must NOT invent new interfaces or modify existing contracts\n\n"
        "## Verification\n"
        "Your output will be verified by:\n"
        "1. Schema validation (L0)\n"
        "2. Structural consistency (L1)\n"
        "3. Running the test suite from the behavior contract (L2)\n"
        "4. Git diff scan for boundary violations (L3)\n\n"
        "If any check fails, you will receive a rejection with diagnostic details.\n"
    )
