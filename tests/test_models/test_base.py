import pytest
from pydantic import ValidationError

from core.models.base import CheckDecl, ContractMeta, ContractRef
from core.models.enums import ContractStatus, ContractType, CreatedBy, FailureAction, Severity


def _validation_block() -> dict:
    return {"schema": "contracts/schemas/role.contract.schema.json", "checks": []}


def _failure_block() -> dict:
    return {"action": FailureAction.RETRY.value, "max_retries": 3, "severity": Severity.MID.value}


def test_contract_ref_allows_exact_and_major_x() -> None:
    ContractRef(id="behavior.user_auth", version="1.0.0")
    ContractRef(id="behavior.user_auth", version="1.x")


def test_contract_ref_allows_event_ids_for_context_refs() -> None:
    ContractRef(id="evidence.run.20260304", version="1.0.0")


def test_contract_meta_rejects_unknown_field() -> None:
    payload = {
        "type": ContractType.ROLE.value,
        "id": "role.coder_backend",
        "version": "1.0.0",
        "status": ContractStatus.ACTIVE.value,
        "created_by": CreatedBy.ARCHITECT.value,
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": _validation_block(),
        "on_failure": _failure_block(),
        "unexpected": "nope",
    }

    with pytest.raises(ValidationError):
        ContractMeta(**payload)


def test_contract_meta_rejects_invalid_version() -> None:
    payload = {
        "type": ContractType.ROLE.value,
        "id": "role.coder_backend",
        "version": "v1.0",
        "status": ContractStatus.ACTIVE.value,
        "created_by": CreatedBy.ARCHITECT.value,
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": _validation_block(),
        "on_failure": _failure_block(),
    }

    with pytest.raises(ValidationError):
        ContractMeta(**payload)


def test_check_decl_requires_run_for_command() -> None:
    with pytest.raises(ValidationError):
        CheckDecl(kind="command")
