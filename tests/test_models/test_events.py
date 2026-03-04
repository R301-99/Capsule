import json
from pathlib import Path

import pytest
from jsonschema import validate
from pydantic import ValidationError

from core.models.evidence import EvidenceContract
from core.models.export_schemas import export_schemas
from core.models.gate_report import GateReportContract
from core.models.human_decision import HumanDecisionContract
from core.models.enums import ContractStatus, CreatedBy


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


def _evidence_payload() -> dict:
    return {
        "meta": meta_payload("evidence", "evidence.run.20260303"),
        "spec": {
            "run_id": "20260303-101530-ab12cd",
            "role_id": "role.coder_backend",
            "task_ref": {"id": "task.user_auth.login_api", "version": "1.0.0"},
            "contract_snapshot": {"refs": [{"id": "interface.user_auth", "version": "1.0.0"}]},
            "changes": {"modified_files": ["src/backend/auth/login.py"], "diff_stat": {"files": 1, "insertions": 10, "deletions": 2}},
            "commands": {"ran": [{"cmd": "pytest -q", "exit_code": 0, "duration_ms": 1200}]},
            "tests": {"ran": [{"cmd": "pytest -q", "exit_code": 0}], "summary": "pass"},
            "self_report": {"confidence": 0.9, "risks": [], "notes": "ok"},
        },
    }


def test_event_contracts_valid() -> None:
    GateReportContract(
        meta=meta_payload("gate_report", "gate_report.output.001"),
        spec={
            "gate_id": "OUTPUT_GATE",
            "level": 2,
            "result": "pass",
            "diagnostics": {"summary": "ok", "details": {}},
            "resolved_refs": [{"id": "behavior.user_auth", "version": "1.0.0"}],
            "timestamp": "2026-03-04T00:00:00Z",
        },
    )

    EvidenceContract(**_evidence_payload())

    HumanDecisionContract(
        meta=meta_payload("human_decision", "human_decision.20260303.001"),
        spec={
            "decision_id": "HD-20260303-001",
            "trigger": "review_required",
            "context_refs": [],
            "options_presented": ["approve", "abort"],
            "selected_option": "approve",
            "actions": {"next": "resume"},
            "timestamp": "2026-03-04T00:00:00Z",
            "made_by": "human",
        },
    )


def test_human_decision_selected_option_must_exist() -> None:
    with pytest.raises(ValidationError):
        HumanDecisionContract(
            meta=meta_payload("human_decision", "human_decision.20260303.001"),
            spec={
                "decision_id": "HD-20260303-001",
                "trigger": "review_required",
                "context_refs": [],
                "options_presented": ["approve", "abort"],
                "selected_option": "amend",
                "actions": {"next": "resume"},
                "timestamp": "2026-03-04T00:00:00Z",
                "made_by": "human",
            },
        )


def test_confidence_out_of_range_rejected() -> None:
    payload = _evidence_payload()
    payload["spec"]["self_report"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        EvidenceContract(**payload)


def test_exported_schemas_exist_and_validate_samples(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    assert written
    assert (tmp_path / "contract.envelope.schema.json").exists()

    schema = json.loads((tmp_path / "evidence.schema.json").read_text(encoding="utf-8"))
    sample = EvidenceContract(**_evidence_payload()).model_dump(mode="json")
    validate(instance=sample, schema=schema)
