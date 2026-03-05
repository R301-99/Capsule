from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from core.models.base import ContractRef
from core.registry import Registry, ResolutionError


@pytest.fixture
def resolution_registry(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> Registry:
    write_yaml("contracts/instances/user_auth/behavior_1_0_0.yaml", payload_factory.behavior(version="1.0.0"))
    write_yaml("contracts/instances/user_auth/behavior_1_1_0.yaml", payload_factory.behavior(version="1.1.0"))
    write_yaml("contracts/instances/user_auth/behavior_1_2_3.yaml", payload_factory.behavior(version="1.2.3"))
    write_yaml(
        "contracts/instances/user_auth/behavior_1_3_0.yaml",
        payload_factory.behavior(version="1.3.0", status="deprecated"),
    )
    write_yaml("contracts/instances/user_auth/behavior_2_0_0.yaml", payload_factory.behavior(version="2.0.0"))

    write_yaml(
        "contracts/instances/legacy/behavior_legacy_1_0_0.yaml",
        payload_factory.behavior(contract_id="behavior.legacy", version="1.0.0", status="deprecated"),
    )

    return Registry.build(project_root)


def test_resolve_exact_version(resolution_registry: Registry) -> None:
    resolved = resolution_registry.resolve(ContractRef(id="behavior.user_auth", version="1.0.0"))

    assert resolved.meta.id == "behavior.user_auth"
    assert resolved.meta.version == "1.0.0"


def test_resolve_major_range_returns_highest_active(resolution_registry: Registry) -> None:
    resolved = resolution_registry.resolve(ContractRef(id="behavior.user_auth", version="1.x"))

    assert resolved.meta.version == "1.2.3"
    assert resolved.meta.status.value == "active"


def test_resolve_exact_missing_raises_resolution_error(resolution_registry: Registry) -> None:
    with pytest.raises(ResolutionError) as error:
        resolution_registry.resolve(ContractRef(id="behavior.user_auth", version="9.0.0"))

    assert error.value.reason == "not_found"


def test_resolve_range_without_active_match_raises_resolution_error(
    resolution_registry: Registry,
) -> None:
    with pytest.raises(ResolutionError) as error:
        resolution_registry.resolve(ContractRef(id="behavior.legacy", version="1.x"))

    assert error.value.reason == "no_active_match"


def test_resolve_range_with_multiple_active_versions_selects_highest(
    resolution_registry: Registry,
) -> None:
    resolved = resolution_registry.resolve(ContractRef(id="behavior.user_auth", version="1.x"))

    assert resolved.meta.version == "1.2.3"


def test_resolve_range_ignores_deprecated_versions(resolution_registry: Registry) -> None:
    resolved = resolution_registry.resolve(ContractRef(id="behavior.user_auth", version="1.x"))

    assert resolved.meta.version != "1.3.0"

