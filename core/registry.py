from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Union

import yaml
from pydantic import ConfigDict, ValidationError

from .models.base import ContractEnvelope, ContractRef, SEMVER_EXACT_PATTERN
from .models.behavior import BehaviorContract
from .models.boundary import BoundaryContract
from .models.enums import ContractStatus, ContractType
from .models.interface import InterfaceContract
from .models.role import RoleContract
from .models.task import TaskContract

LoadableContract = Union[RoleContract, TaskContract, InterfaceContract, BehaviorContract, BoundaryContract]

_YAML_SUFFIXES = {".yaml", ".yml"}
_MAJOR_RANGE_PATTERN = re.compile(r"^(?P<major>\d+)\.x$")
_SEMVER_PATTERN = re.compile(SEMVER_EXACT_PATTERN)
_RUNTIME_TYPES = {
    ContractType.GATE_REPORT.value,
    ContractType.EVIDENCE.value,
    ContractType.HUMAN_DECISION.value,
}
_TYPE_TO_MODEL = {
    ContractType.ROLE.value: RoleContract,
    ContractType.TASK.value: TaskContract,
    ContractType.INTERFACE.value: InterfaceContract,
    ContractType.BEHAVIOR.value: BehaviorContract,
    ContractType.BOUNDARY.value: BoundaryContract,
}


@dataclass(frozen=True)
class LoadSuccess:
    file_path: Path
    contract_id: str
    contract_version: str
    contract_type: ContractType


@dataclass(frozen=True)
class LoadError:
    file_path: Path
    error_type: str
    message: str
    details: dict[str, Any] | None = None


class ResolutionError(Exception):
    def __init__(self, ref: ContractRef, reason: str, candidates: list[str] | None = None) -> None:
        self.ref = ref
        self.reason = reason
        self.candidates = candidates or []
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        if self.reason == "not_found":
            return f"Contract {self.ref.id}@{self.ref.version} not found"
        if self.reason == "no_active_match":
            return f"No active version matching {self.ref.id}@{self.ref.version}"
        if self.reason == "ambiguous":
            return f"Ambiguous resolution for {self.ref.id}@{self.ref.version}"
        return f"Failed to resolve {self.ref.id}@{self.ref.version}"


class _FrozenContractRef(ContractRef):
    model_config = ConfigDict(frozen=True)


class Registry:
    def __init__(
        self,
        *,
        project_root: Path,
        by_id_version: dict[tuple[str, str], LoadableContract],
        by_id: dict[str, list[LoadableContract]],
        by_type: dict[ContractType, list[LoadableContract]],
        path_index: dict[tuple[str, str], Path],
        load_successes: list[LoadSuccess],
        load_errors: list[LoadError],
        boundary_load_errors: list[LoadError],
    ) -> None:
        self._project_root = project_root
        self._by_id_version = dict(by_id_version)
        self._by_id = {contract_id: tuple(versions) for contract_id, versions in by_id.items()}
        self._by_type = {contract_type: tuple(items) for contract_type, items in by_type.items()}
        self._path_index = dict(path_index)
        self._load_successes = tuple(load_successes)
        self._load_errors = tuple(load_errors)
        self._boundary_load_errors = tuple(boundary_load_errors)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def load_successes(self) -> tuple[LoadSuccess, ...]:
        return self._load_successes

    @property
    def load_errors(self) -> tuple[LoadError, ...]:
        return self._load_errors

    @property
    def boundary_load_errors(self) -> tuple[LoadError, ...]:
        return self._boundary_load_errors

    @property
    def path_index(self) -> dict[tuple[str, str], Path]:
        return dict(self._path_index)

    def is_boundary_intact(self) -> bool:
        return not self._boundary_load_errors

    @classmethod
    def build(cls, project_root: Path) -> Registry:
        root = Path(project_root)
        if not root.exists():
            raise FileNotFoundError(f"project_root does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"project_root is not a directory: {root}")

        by_id_version: dict[tuple[str, str], LoadableContract] = {}
        path_index: dict[tuple[str, str], Path] = {}
        load_successes: list[LoadSuccess] = []
        load_errors: list[LoadError] = []
        boundary_load_errors: list[LoadError] = []

        scan_roots = [
            (root / "roles", False),
            (root / "contracts" / "boundaries", True),
            (root / "contracts" / "instances", False),
        ]

        for scan_root, is_boundary_scan in scan_roots:
            for file_path in cls._iter_yaml_files(scan_root):
                cls._load_file(
                    file_path=file_path,
                    is_boundary_scan=is_boundary_scan,
                    by_id_version=by_id_version,
                    path_index=path_index,
                    load_successes=load_successes,
                    load_errors=load_errors,
                    boundary_load_errors=boundary_load_errors,
                )

        by_id: dict[str, list[LoadableContract]] = {}
        by_type: dict[ContractType, list[LoadableContract]] = {contract_type: [] for contract_type in ContractType}
        for contract in by_id_version.values():
            by_id.setdefault(contract.meta.id, []).append(contract)
            by_type[contract.meta.type].append(contract)
        for versions in by_id.values():
            versions.sort(key=lambda item: cls._semver_tuple(item.meta.version), reverse=True)

        return cls(
            project_root=root,
            by_id_version=by_id_version,
            by_id=by_id,
            by_type=by_type,
            path_index=path_index,
            load_successes=load_successes,
            load_errors=load_errors,
            boundary_load_errors=boundary_load_errors,
        )

    @classmethod
    def _iter_yaml_files(cls, scan_root: Path) -> Iterable[Path]:
        if not scan_root.exists() or not scan_root.is_dir():
            return

        for current_root, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = sorted(name for name in dirnames if not cls._is_ignored_name(name))
            for filename in sorted(filenames):
                if cls._is_ignored_name(filename):
                    continue
                if Path(filename).suffix.lower() not in _YAML_SUFFIXES:
                    continue
                yield Path(current_root) / filename

    @staticmethod
    def _is_ignored_name(name: str) -> bool:
        return name.startswith(".") or name.startswith("_")

    @classmethod
    def _load_file(
        cls,
        *,
        file_path: Path,
        is_boundary_scan: bool,
        by_id_version: dict[tuple[str, str], LoadableContract],
        path_index: dict[tuple[str, str], Path],
        load_successes: list[LoadSuccess],
        load_errors: list[LoadError],
        boundary_load_errors: list[LoadError],
    ) -> None:
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            cls._record_error(
                file_path=file_path,
                error_type="file_read_error",
                message=f"Failed to read file: {exc}",
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan,
            )
            return

        try:
            payload = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            cls._record_error(
                file_path=file_path,
                error_type="yaml_parse_error",
                message=f"Failed to parse YAML: {exc}",
                details={"error": str(exc)},
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan,
            )
            return

        contract_payload = cls._extract_contract_payload(payload)
        if contract_payload is None:
            cls._record_error(
                file_path=file_path,
                error_type="missing_meta_type",
                message="Missing contract.meta.type",
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan,
            )
            return

        meta_obj = contract_payload.get("meta")
        contract_type_value = meta_obj.get("type") if isinstance(meta_obj, dict) else None
        if not isinstance(contract_type_value, str) or not contract_type_value:
            cls._record_error(
                file_path=file_path,
                error_type="missing_meta_type",
                message="Missing contract.meta.type",
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan,
            )
            return

        if contract_type_value in _RUNTIME_TYPES:
            return

        model_cls = _TYPE_TO_MODEL.get(contract_type_value)
        if model_cls is None:
            cls._record_error(
                file_path=file_path,
                error_type="unknown_contract_type",
                message=f"Unknown contract type: {contract_type_value}",
                details={"contract_type": contract_type_value},
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan,
            )
            return

        try:
            contract = model_cls(**contract_payload)
        except ValidationError as exc:
            cls._record_error(
                file_path=file_path,
                error_type="validation_error",
                message=f"L0 validation failed: {exc}",
                details={"errors": exc.errors()},
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan or contract_type_value == ContractType.BOUNDARY.value,
            )
            return

        key = (contract.meta.id, contract.meta.version)
        if key in by_id_version:
            existing_path = path_index.get(key)
            details = {"contract_id": key[0], "contract_version": key[1]}
            if existing_path is not None:
                details["existing_file"] = str(existing_path)
            cls._record_error(
                file_path=file_path,
                error_type="duplicate_contract",
                message=f"Duplicate contract detected: {contract.meta.id}@{contract.meta.version}",
                details=details,
                load_errors=load_errors,
                boundary_load_errors=boundary_load_errors,
                is_boundary_error=is_boundary_scan or contract.meta.type == ContractType.BOUNDARY,
            )
            return

        by_id_version[key] = contract
        path_index[key] = file_path
        load_successes.append(
            LoadSuccess(
                file_path=file_path,
                contract_id=contract.meta.id,
                contract_version=contract.meta.version,
                contract_type=contract.meta.type,
            )
        )

    @staticmethod
    def _extract_contract_payload(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        embedded = payload.get("contract")
        if isinstance(embedded, dict):
            return embedded
        return payload

    @staticmethod
    def _record_error(
        *,
        file_path: Path,
        error_type: str,
        message: str,
        load_errors: list[LoadError],
        boundary_load_errors: list[LoadError],
        is_boundary_error: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        error = LoadError(file_path=file_path, error_type=error_type, message=message, details=details)
        load_errors.append(error)
        if is_boundary_error:
            boundary_load_errors.append(error)

    @staticmethod
    def _semver_tuple(version: str) -> tuple[int, int, int]:
        major, minor, patch = version.split(".")
        return (int(major), int(minor), int(patch))

    def get_exact(self, contract_id: str, version: str) -> LoadableContract | None:
        return self._by_id_version.get((contract_id, version))

    def get_latest_active(self, contract_id: str) -> LoadableContract | None:
        for contract in self._by_id.get(contract_id, ()):
            if contract.meta.status == ContractStatus.ACTIVE:
                return contract
        return None

    def list_versions(self, contract_id: str) -> list[LoadableContract]:
        return list(self._by_id.get(contract_id, ()))

    def list_by_type(self, contract_type: ContractType) -> list[LoadableContract]:
        return list(self._by_type.get(contract_type, ()))

    def all_contracts(self) -> list[LoadableContract]:
        return list(self._by_id_version.values())

    def has(self, contract_id: str, version: str) -> bool:
        return (contract_id, version) in self._by_id_version

    def resolve(self, ref: ContractRef) -> LoadableContract:
        if _SEMVER_PATTERN.match(ref.version):
            exact = self.get_exact(ref.id, ref.version)
            if exact is None:
                candidates = [contract.meta.version for contract in self._by_id.get(ref.id, ())]
                raise ResolutionError(ref=ref, reason="not_found", candidates=candidates)
            return exact

        range_match = _MAJOR_RANGE_PATTERN.match(ref.version)
        if range_match:
            major = int(range_match.group("major"))
            candidates = [
                contract
                for contract in self._by_id.get(ref.id, ())
                if self._semver_tuple(contract.meta.version)[0] == major and contract.meta.status == ContractStatus.ACTIVE
            ]
            if not candidates:
                versions = [
                    f"{contract.meta.version}:{contract.meta.status.value}"
                    for contract in self._by_id.get(ref.id, ())
                    if self._semver_tuple(contract.meta.version)[0] == major
                ]
                raise ResolutionError(ref=ref, reason="no_active_match", candidates=versions)
            return candidates[0]

        raise ResolutionError(ref=ref, reason="not_found", candidates=[])

    def check_deps_exist(self, contract: ContractEnvelope) -> list[ContractRef]:
        missing: list[ContractRef] = []
        for dep in contract.meta.dependencies:
            try:
                self.resolve(dep)
            except ResolutionError:
                missing.append(dep)
        return missing

    def resolve_all_refs(self, refs: list[ContractRef]) -> dict[ContractRef, LoadableContract]:
        resolved: dict[ContractRef, LoadableContract] = {}
        for ref in refs:
            try:
                contract = self.resolve(ref)
            except ResolutionError:
                continue
            resolved[_FrozenContractRef(id=ref.id, version=ref.version)] = contract
        return resolved
