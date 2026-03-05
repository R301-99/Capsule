from __future__ import annotations

import re
from typing import Any

from core.models.base import ContractRef
from core.models.enums import GateLevel, GateResult


def test_input_gate_passes_and_resolves_exact_refs(build_env) -> None:
    env = build_env()

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is True
    assert result.rejection is None
    assert result.gate_report["result"] == GateResult.PASS
    assert result.gate_report["level"] == GateLevel.L1
    assert result.resolved_refs
    for ref in result.resolved_refs:
        assert re.match(r"^\d+\.\d+\.\d+$", ref.version)


def test_input_gate_fails_l0_when_task_missing(build_env) -> None:
    env = build_env()

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.missing", version="1.0.0"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.gate_report["level"] == GateLevel.L0
    assert result.gate_report["result"] == GateResult.FAIL
    assert result.rejection is not None


def test_input_gate_fails_l0_when_role_missing(build_env) -> None:
    env = build_env(include_role=False)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.gate_report["level"] == GateLevel.L0
    assert result.rejection is not None


def test_input_gate_fails_l1_when_behavior_ref_missing(build_env, payload_factory: Any) -> None:
    bad_task = payload_factory.task(behavior_ref={"id": "behavior.missing", "version": "1.x"})
    env = build_env(task_payload=bad_task)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.gate_report["level"] == GateLevel.L1
    assert result.rejection is not None
    assert "behavior" in result.rejection.failure_details.summary.lower()


def test_input_gate_fails_l1_when_scope_exceeds_role_capabilities(build_env, payload_factory: Any) -> None:
    role = payload_factory.role(write_capabilities=["src/backend/**"])
    task = payload_factory.task(scope_include=["src/frontend/**"])
    env = build_env(role_payload=role, task_payload=task)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.gate_report["level"] == GateLevel.L1
    assert result.rejection is not None
    assert "scope" in result.rejection.failure_details.summary.lower()


def test_input_gate_fails_l1_when_scope_hits_role_prohibition(build_env, payload_factory: Any) -> None:
    task = payload_factory.task(scope_include=["state/private/**"])
    env = build_env(task_payload=task)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.gate_report["level"] == GateLevel.L1
    assert result.rejection is not None


def test_input_gate_fails_l1_when_behavior_created_by_not_allowed(build_env, payload_factory: Any) -> None:
    behavior = payload_factory.behavior(created_by="role.coder_backend")
    env = build_env(behavior_payload=behavior)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.gate_report["level"] == GateLevel.L1
    assert result.rejection is not None

