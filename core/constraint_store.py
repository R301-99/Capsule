from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from .models.constraint import Constraint


class ConstraintStoreError(Exception):
    pass


class ConstraintStore:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = Path(state_dir)
        self._constraints_path = self._state_dir / "constraints.json"

    @property
    def constraints_path(self) -> Path:
        return self._constraints_path

    def load(self) -> list[Constraint]:
        if not self._constraints_path.exists():
            return []
        try:
            raw = self._constraints_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConstraintStoreError(f"Failed to read constraints store: {exc}") from exc

        items = payload.get("constraints", [])
        if not isinstance(items, list):
            raise ConstraintStoreError("constraints.json must contain a list at key 'constraints'")

        try:
            return [Constraint(**item) for item in items]
        except (TypeError, ValidationError) as exc:
            raise ConstraintStoreError(f"Invalid constraints payload: {exc}") from exc

    def save(self, constraints: list[Constraint]) -> None:
        payload = {"constraints": [constraint.model_dump(mode="json") for constraint in constraints]}
        self._write_json_atomic(self._constraints_path, payload)

    def add(self, constraint: Constraint) -> list[Constraint]:
        constraints = self.load()
        normalized = self._normalize_id(constraints, constraint)
        constraints.append(normalized)
        return constraints

    def add_batch(self, constraints: list[Constraint]) -> list[Constraint]:
        merged = self.load()
        for constraint in constraints:
            merged.append(self._normalize_id(merged, constraint))
        return merged

    def query(
        self,
        category: str | None = None,
        source: str | None = None,
        enforcement: str | None = None,
        frozen: bool | None = None,
    ) -> list[Constraint]:
        result = self.load()
        if category is not None:
            result = [item for item in result if item.category == category]
        if source is not None:
            result = [item for item in result if item.source.value == source]
        if enforcement is not None:
            result = [item for item in result if item.enforcement.value == enforcement]
        if frozen is not None:
            result = [item for item in result if item.frozen == frozen]
        return result

    def count(self) -> int:
        return len(self.load())

    def get_test_constraints(self) -> list[Constraint]:
        return self.query(enforcement="test")

    def get_policy_constraints(self) -> list[Constraint]:
        return self.query(enforcement="policy")

    def _normalize_id(self, existing: list[Constraint], candidate: Constraint) -> Constraint:
        existing_ids = {item.id for item in existing}
        if candidate.id not in existing_ids:
            return candidate
        new_id = self._next_id(existing_ids)
        data = candidate.model_dump(mode="json")
        data["id"] = new_id
        return Constraint(**data)

    @staticmethod
    def _next_id(existing_ids: set[str]) -> str:
        index = 1
        while True:
            proposal = f"C-{index:03d}"
            if proposal not in existing_ids:
                return proposal
            index += 1

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            tmp_path.write_text(encoded, encoding="utf-8")
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
