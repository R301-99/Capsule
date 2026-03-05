from __future__ import annotations

from enum import Enum
from typing import Any

import yaml

from .models.workflow import WorkflowNode


def build_prompt(
    node: WorkflowNode,
    task_contract: dict[str, Any],
    interface_contracts: list[dict[str, Any]],
    behavior_contract: dict[str, Any],
    role_contract: dict[str, Any],
    state_snapshot: dict[str, Any],
    rejection_history: list[dict[str, Any]] | None = None,
) -> str:
    role_name = _nested_get(role_contract, "spec", "display_name") or node.role
    scope_include = _nested_get(task_contract, "spec", "scope", "include") or []
    scope_exclude = _nested_get(task_contract, "spec", "scope", "exclude") or []

    lines = [
        f"# Role\nYou are {role_name}.",
        "",
        "# Constraints",
        f"You MUST only modify files within: {scope_include}",
        f"You MUST NOT modify: {scope_exclude}",
        "",
        "# Task",
        _dump_yaml(task_contract),
        "",
        "# Interface Contract",
        _dump_yaml(interface_contracts),
        "",
        "# Behavior Contract (Tests you must pass)",
        _dump_yaml(behavior_contract),
        "",
        "# Role Contract",
        _dump_yaml(role_contract),
        "",
        "# Current Project State",
        _dump_yaml(state_snapshot),
    ]

    if rejection_history:
        lines.extend(["", "# Previous Failures (if any)", _dump_yaml(rejection_history)])

    lines.extend(
        [
            "",
            "# Instructions",
            "Implement the task according to the contracts above.",
            "Your output will be verified against the behavior contract.",
            "Do not modify any files outside your authorized scope.",
        ]
    )
    return "\n".join(lines).strip()


def _dump_yaml(payload: Any) -> str:
    return yaml.safe_dump(_normalize_yaml_payload(payload), sort_keys=False, allow_unicode=True).strip()


def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _normalize_yaml_payload(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        return _normalize_yaml_payload(payload.model_dump(mode="json"))
    if isinstance(payload, Enum):
        return payload.value
    if isinstance(payload, dict):
        return {str(key): _normalize_yaml_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_normalize_yaml_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [_normalize_yaml_payload(item) for item in payload]
    if payload is None or isinstance(payload, (str, int, float, bool)):
        return payload
    return str(payload)
