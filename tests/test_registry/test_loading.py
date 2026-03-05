from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.registry import Registry


def test_build_loads_valid_contracts(
    project_root: Path, populate_valid_contracts: Callable[[], dict[str, Path]]
) -> None:
    populate_valid_contracts()

    registry = Registry.build(project_root)

    assert len(registry.load_successes) == 5
    assert not registry.load_errors
    assert {(item.contract_id, item.contract_version) for item in registry.load_successes} == {
        ("role.coder_backend", "1.0.0"),
        ("boundary.global", "1.0.0"),
        ("behavior.user_auth", "1.0.0"),
        ("interface.user_auth", "1.0.0"),
        ("task.user_auth.login_api", "1.0.0"),
    }


def test_records_yaml_parse_error(
    project_root: Path, write_yaml: Callable[[str, Any], Path]
) -> None:
    write_yaml("roles/broken.yaml", "meta:\n  type: role\n  id: role.coder_backend\nspec: [")

    registry = Registry.build(project_root)

    assert len(registry.load_errors) == 1
    assert registry.load_errors[0].error_type == "yaml_parse_error"


def test_records_missing_meta_type(
    project_root: Path, write_yaml: Callable[[str, Any], Path]
) -> None:
    write_yaml("roles/missing_type.yaml", {"meta": {"id": "role.coder_backend"}, "spec": {}})

    registry = Registry.build(project_root)

    assert len(registry.load_errors) == 1
    assert registry.load_errors[0].error_type == "missing_meta_type"


def test_records_unknown_contract_type(
    project_root: Path, write_yaml: Callable[[str, Any], Path]
) -> None:
    write_yaml("roles/unknown_type.yaml", {"meta": {"type": "unknown", "id": "x", "version": "1.0.0"}, "spec": {}})

    registry = Registry.build(project_root)

    assert len(registry.load_errors) == 1
    assert registry.load_errors[0].error_type == "unknown_contract_type"


def test_records_validation_error_for_invalid_l0_payload(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> None:
    bad_role = payload_factory.role()
    del bad_role["spec"]["capabilities"]
    write_yaml("roles/invalid_role.yaml", bad_role)

    registry = Registry.build(project_root)

    assert len(registry.load_errors) == 1
    assert registry.load_errors[0].error_type == "validation_error"
    assert registry.load_errors[0].details is not None


def test_records_duplicate_contract_and_keeps_first(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> None:
    write_yaml("roles/role_a.yaml", payload_factory.role(contract_id="role.coder_backend", version="1.0.0"))
    write_yaml("roles/role_b.yaml", payload_factory.role(contract_id="role.coder_backend", version="1.0.0"))

    registry = Registry.build(project_root)

    assert len(registry.load_successes) == 1
    assert len(registry.load_errors) == 1
    assert registry.load_errors[0].error_type == "duplicate_contract"


def test_missing_scan_directories_are_skipped(project_root: Path) -> None:
    registry = Registry.build(project_root)

    assert not registry.load_successes
    assert not registry.load_errors


def test_empty_scan_directories_are_allowed(project_root: Path) -> None:
    (project_root / "roles").mkdir(parents=True)
    (project_root / "contracts" / "boundaries").mkdir(parents=True)
    (project_root / "contracts" / "instances").mkdir(parents=True)

    registry = Registry.build(project_root)

    assert not registry.load_successes
    assert not registry.load_errors


def test_runtime_event_contract_file_is_skipped(
    project_root: Path, write_yaml: Callable[[str, Any], Path]
) -> None:
    write_yaml(
        "contracts/instances/runtime/evidence.yaml",
        {"meta": {"type": "evidence"}, "spec": {"note": "runtime generated"}},
    )

    registry = Registry.build(project_root)

    assert not registry.load_successes
    assert not registry.load_errors


def test_ignores_hidden_and_private_prefixed_paths(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> None:
    write_yaml("roles/.hidden.yaml", payload_factory.role(contract_id="role.hidden"))
    write_yaml("roles/_private.yaml", payload_factory.role(contract_id="role.private"))
    write_yaml("roles/.shadow/inner.yaml", payload_factory.role(contract_id="role.shadow"))
    write_yaml("roles/_shadow/inner.yaml", payload_factory.role(contract_id="role.shadow_private"))
    write_yaml("roles/visible.yaml", payload_factory.role(contract_id="role.visible"))

    registry = Registry.build(project_root)

    assert len(registry.load_successes) == 1
    assert registry.load_successes[0].contract_id == "role.visible"
    assert not registry.load_errors


def test_boundary_intact_true_when_boundary_loaded(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> None:
    write_yaml("contracts/boundaries/global.yaml", payload_factory.boundary())

    registry = Registry.build(project_root)

    assert registry.is_boundary_intact() is True
    assert not registry.boundary_load_errors


def test_boundary_intact_false_when_boundary_has_l0_error(
    project_root: Path, write_yaml: Callable[[str, Any], Path], payload_factory: Any
) -> None:
    bad_boundary = payload_factory.boundary()
    bad_boundary["spec"]["sacred_files"] = []
    write_yaml("contracts/boundaries/bad.yaml", bad_boundary)

    registry = Registry.build(project_root)

    assert registry.is_boundary_intact() is False
    assert len(registry.boundary_load_errors) == 1
    assert registry.boundary_load_errors[0].error_type == "validation_error"
