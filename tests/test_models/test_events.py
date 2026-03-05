import json
from pathlib import Path

import pytest
from jsonschema import validate
from pydantic import ValidationError

from core.models.evidence import EvidenceContract
from core.models.export_schemas import export_schemas
from core.models.gate_report import GateReportContract
from core.models.human_decision import HumanDecisionContract


def _meta(contract_type: str, contract_id: str) -> dict:
    return {
        "type": contract_type,
        "id": contract_id,
        "version": "1.0.0",
        "status": "active",
        "created_by": "system",
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": {"schema": "contracts/schemas/placeholder.json", "checks": []},
        "on_failure": {"action": "retry", "max_retries": 3, "severity": "mid"},
    }


def test_event_models_and_schema_validation(tmp_path: Path) -> None:
    export_schemas(tmp_path)

    gate_payload = {
        "meta": _meta("gate_report", "gate_report.output.main"),
        "spec": {
            "gate_id": "OUTPUT_GATE",
            "level": 2,
            "result": "pass",
            "diagnostics": {"summary": "ok", "details": {}},
            "resolved_refs": [{"id": "behavior.user_auth", "version": "1.0.0"}],
            "timestamp": "2026-03-04T00:00:00Z",
        },
        "extensions": {},
    }
    gate = GateReportContract(**gate_payload)

    evidence_payload = {
        "meta": _meta("evidence", "evidence.run.20260304"),
        "spec": {
            "run_id": "20260304-120000-ab12cd",
            "role_id": "role.coder_backend",
            "task_ref": {"id": "task.user_auth.login_api", "version": "1.0.0"},
            "contract_snapshot": {"refs": [{"id": "behavior.user_auth", "version": "1.0.0"}]},
            "changes": {"modified_files": ["src/backend/auth.py"], "diff_stat": {"files": 1, "insertions": 10, "deletions": 1}},
            "commands": {"ran": [{"cmd": "pytest -q", "exit_code": 0, "duration_ms": 100}]},
            "tests": {"ran": [{"cmd": "pytest -q", "exit_code": 0, "duration_ms": 100}], "summary": "pass"},
            "self_report": {"confidence": 0.9, "risks": [], "notes": "stable"},
        },
        "extensions": {},
    }
    evidence = EvidenceContract(**evidence_payload)

    decision_payload = {
        "meta": _meta("human_decision", "human_decision.main.001"),
        "spec": {
            "decision_id": "HD-20260304-001",
            "trigger": "review_required",
            "context_refs": [{"id": "evidence.run.abc", "version": "1.0.0"}],
            "options_presented": ["approve", "amend_contract"],
            "selected_option": "amend_contract",
            "actions": {"next": "amend_contract"},
            "timestamp": "2026-03-04T00:00:00Z",
            "made_by": "human",
        },
        "extensions": {},
    }
    decision = HumanDecisionContract(**decision_payload)

    for model, schema_file in [
        (gate, "gate_report.schema.json"),
        (evidence, "evidence.schema.json"),
        (decision, "human_decision.schema.json"),
    ]:
        schema = json.loads((tmp_path / schema_file).read_text(encoding="utf-8"))
        validate(instance=model.model_dump(mode="json"), schema=schema)


def test_human_decision_selected_option_must_exist() -> None:
    payload = {
        "meta": _meta("human_decision", "human_decision.main.001"),
        "spec": {
            "decision_id": "HD-20260304-001",
            "trigger": "review_required",
            "context_refs": [],
            "options_presented": ["approve"],
            "selected_option": "reject",
            "actions": {"next": "pause"},
            "timestamp": "2026-03-04T00:00:00Z",
            "made_by": "human",
        },
    }

    with pytest.raises(ValidationError):
        HumanDecisionContract(**payload)


def test_confidence_out_of_range_is_rejected() -> None:
    payload = {
        "meta": _meta("evidence", "evidence.run.20260304"),
        "spec": {
            "run_id": "20260304-120000-ab12cd",
            "role_id": "role.coder_backend",
            "task_ref": {"id": "task.user_auth.login_api", "version": "1.0.0"},
            "contract_snapshot": {"refs": [{"id": "behavior.user_auth", "version": "1.0.0"}]},
            "changes": {"modified_files": [], "diff_stat": {"files": 0, "insertions": 0, "deletions": 0}},
            "commands": {"ran": []},
            "tests": {"ran": [], "summary": "fail"},
            "self_report": {"confidence": 1.2, "risks": []},
        },
    }

    with pytest.raises(ValidationError):
        EvidenceContract(**payload)
