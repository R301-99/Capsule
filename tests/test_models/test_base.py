import pytest
from pydantic import ValidationError

from core.models.base import ContractMeta, ContractRef
from core.models.enums import ContractStatus, ContractType, CreatedBy, FailureAction


def _meta_payload() -> dict:
    return {
        "type": ContractType.ROLE,
        "id": "role.core.architect",
        "version": "1.0.0",
        "status": ContractStatus.ACTIVE,
        "created_by": CreatedBy.SYSTEM,
        "created_at": "2026-03-04T00:00:00Z",
        "dependencies": [],
        "validation": {"schema": "contracts/schemas/role.contract.schema.json", "checks": []},
        "on_failure": {"action": FailureAction.RETRY, "max_retries": 3, "severity": "mid"},
    }


def test_contract_ref_supports_exact_and_major_range() -> None:
    ContractRef(id="task.user_auth.login_api", version="1.0.0")
    ContractRef(id="task.user_auth.login_api", version="1.x")


def test_contract_meta_rejects_unknown_fields() -> None:
    payload = _meta_payload()
    payload["unknown"] = "x"
    with pytest.raises(ValidationError):
        ContractMeta(**payload)


def test_contract_meta_rejects_invalid_version() -> None:
    payload = _meta_payload()
    payload["version"] = "1.0"
    with pytest.raises(ValidationError):
        ContractMeta(**payload)
