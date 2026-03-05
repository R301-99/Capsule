from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from core.models.base import ContractRef
from core.models.enums import ContractType
from core.registry import Registry


@pytest.fixture
def indexed_registry(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> Registry:
    write_yaml("roles/coder_backend.yaml", payload_factory.role())
    write_yaml("contracts/boundaries/global.yaml", payload_factory.boundary())

    write_yaml(
        "contracts/instances/user_auth/behavior_1_0_0.yaml",
        payload_factory.behavior(version="1.0.0", status="active"),
    )
    write_yaml(
        "contracts/instances/user_auth/behavior_1_1_0.yaml",
        payload_factory.behavior(version="1.1.0", status="deprecated"),
    )
    write_yaml(
        "contracts/instances/user_auth/behavior_1_2_0.yaml",
        payload_factory.behavior(version="1.2.0", status="active"),
    )
    write_yaml(
        "contracts/instances/user_auth/behavior_2_0_0.yaml",
        payload_factory.behavior(version="2.0.0", status="active"),
    )

    write_yaml("contracts/instances/user_auth/interface.yaml", payload_factory.interface(version="1.0.0"))
    write_yaml(
        "contracts/instances/user_auth/task_ok.yaml",
        payload_factory.task(
            contract_id="task.user_auth.ok",
            dependencies=[
                {"id": "behavior.user_auth", "version": "1.x"},
                {"id": "interface.user_auth", "version": "1.0.0"},
            ],
        ),
    )
    write_yaml(
        "contracts/instances/user_auth/task_missing.yaml",
        payload_factory.task(
            contract_id="task.user_auth.missing",
            dependencies=[
                {"id": "behavior.missing", "version": "1.0.0"},
                {"id": "interface.user_auth", "version": "2.0.0"},
            ],
        ),
    )

    return Registry.build(project_root)


def test_get_exact_returns_contract(indexed_registry: Registry) -> None:
    contract = indexed_registry.get_exact("behavior.user_auth", "1.2.0")

    assert contract is not None
    assert contract.meta.id == "behavior.user_auth"
    assert contract.meta.version == "1.2.0"


def test_get_exact_returns_none_when_missing(indexed_registry: Registry) -> None:
    assert indexed_registry.get_exact("behavior.user_auth", "9.9.9") is None


def test_get_latest_active_returns_highest_active_version(indexed_registry: Registry) -> None:
    latest = indexed_registry.get_latest_active("behavior.user_auth")

    assert latest is not None
    assert latest.meta.version == "2.0.0"
    assert latest.meta.status.value == "active"


def test_get_latest_active_returns_none_without_active(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> None:
    write_yaml(
        "contracts/instances/deprecated/behavior.yaml",
        payload_factory.behavior(contract_id="behavior.legacy", version="1.0.0", status="deprecated"),
    )
    registry = Registry.build(project_root)

    assert registry.get_latest_active("behavior.legacy") is None


def test_list_versions_returns_descending_semver(indexed_registry: Registry) -> None:
    versions = [item.meta.version for item in indexed_registry.list_versions("behavior.user_auth")]

    assert versions == ["2.0.0", "1.2.0", "1.1.0", "1.0.0"]


def test_list_by_type_returns_contracts_for_type(indexed_registry: Registry) -> None:
    roles = indexed_registry.list_by_type(ContractType.ROLE)

    assert len(roles) == 1
    assert roles[0].meta.id == "role.coder_backend"


def test_has_returns_expected_boolean(indexed_registry: Registry) -> None:
    assert indexed_registry.has("behavior.user_auth", "1.0.0") is True
    assert indexed_registry.has("behavior.user_auth", "3.0.0") is False


def test_all_contracts_returns_all_loaded(indexed_registry: Registry) -> None:
    assert len(indexed_registry.all_contracts()) == 9


def test_path_index_contains_source_file(indexed_registry: Registry) -> None:
    path_index = indexed_registry.path_index
    path = path_index[("task.user_auth.ok", "1.0.0")]

    assert path.name == "task_ok.yaml"


def test_check_deps_exist_returns_empty_when_all_present(indexed_registry: Registry) -> None:
    task_contract = indexed_registry.get_exact("task.user_auth.ok", "1.0.0")
    assert task_contract is not None

    assert indexed_registry.check_deps_exist(task_contract) == []


def test_check_deps_exist_returns_missing_refs(indexed_registry: Registry) -> None:
    task_contract = indexed_registry.get_exact("task.user_auth.missing", "1.0.0")
    assert task_contract is not None

    missing = indexed_registry.check_deps_exist(task_contract)
    missing_pairs = {(item.id, item.version) for item in missing}
    assert missing_pairs == {("behavior.missing", "1.0.0"), ("interface.user_auth", "2.0.0")}


def test_resolve_all_refs_collects_resolved_without_raising(indexed_registry: Registry) -> None:
    result = indexed_registry.resolve_all_refs(
        [
            ContractRef(id="behavior.user_auth", version="1.x"),
            ContractRef(id="behavior.unknown", version="1.0.0"),
        ]
    )

    assert len(result) == 1
    resolved_ref = next(iter(result))
    assert resolved_ref.id == "behavior.user_auth"
    assert resolved_ref.version == "1.x"
