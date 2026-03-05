from __future__ import annotations

from typing import Any

from core.models.base import ContractRef
from core.models.enums import GateId, GateLevel


def _prepare_run(env: dict):
    registry = env["registry"]
    state_manager = env["state_manager"]
    validator = env["validator"]
    state = env["state"]

    task_contract = registry.resolve(ContractRef(id="task.user_auth.login_api", version="1.x"))
    task_ref = ContractRef(id=task_contract.meta.id, version=task_contract.meta.version)
    state, run = state_manager.create_run(state, task_ref, "role.coder_backend", "coder_backend")
    input_result = validator.input_gate(state, task_ref, "role.coder_backend")
    assert input_result.passed is True
    state_manager.lock_refs(state, input_result.resolved_refs)
    env["state"] = state
    return state, run, input_result.resolved_refs


def _valid_evidence(run_id: str, task_ref: ContractRef, snapshot_refs: list[ContractRef]) -> dict[str, Any]:
    command_record = {"cmd": "pytest -q tests/backend/test_auth.py", "exit_code": 0, "duration_ms": 120}
    return {
        "run_id": run_id,
        "role_id": "role.coder_backend",
        "task_ref": {"id": task_ref.id, "version": task_ref.version},
        "contract_snapshot": {"refs": [ref.model_dump(mode="json") for ref in snapshot_refs]},
        "changes": {"modified_files": ["src/backend/auth.py"], "diff_stat": {"files": 1, "insertions": 4, "deletions": 1}},
        "commands": {"ran": [command_record]},
        "tests": {"ran": [command_record], "summary": "pass"},
        "self_report": {"confidence": 0.92, "risks": [], "notes": "done"},
    }


def test_input_gate_rejection_contains_failed_gate_and_level(build_env, payload_factory: Any) -> None:
    bad_task = payload_factory.task(behavior_ref={"id": "behavior.missing", "version": "1.x"})
    env = build_env(task_payload=bad_task)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.passed is False
    assert result.rejection is not None
    assert result.rejection.failed_gate == GateId.INPUT_GATE
    assert result.rejection.failed_level == GateLevel.L1
    assert result.rejection.failure_details.summary


def test_output_gate_l0_rejection_contains_failed_gate_and_level(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)
    evidence = _valid_evidence(run.run_id, run.task_ref, locked_refs)
    del evidence["self_report"]

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=evidence,
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.passed is False
    assert result.rejection is not None
    assert result.rejection.failed_gate == GateId.OUTPUT_GATE
    assert result.rejection.failed_level == GateLevel.L0


def test_output_gate_l1_rejection_contains_failed_gate_and_level(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)
    evidence = _valid_evidence(run.run_id, run.task_ref, locked_refs)
    evidence["task_ref"] = {"id": run.task_ref.id, "version": "9.9.9"}

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=evidence,
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.passed is False
    assert result.rejection is not None
    assert result.rejection.failed_gate == GateId.OUTPUT_GATE
    assert result.rejection.failed_level == GateLevel.L1


def test_rejection_max_retries_prefers_task_over_role(build_env, payload_factory: Any) -> None:
    role = payload_factory.role(retry_max=2)
    task = payload_factory.task(
        max_retries=7,
        behavior_ref={"id": "behavior.missing", "version": "1.x"},
    )
    env = build_env(role_payload=role, task_payload=task)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.x"),
        role_id="role.coder_backend",
    )

    assert result.rejection is not None
    assert result.rejection.max_retries == 7


def test_rejection_max_retries_prefers_role_when_task_unavailable(build_env, payload_factory: Any) -> None:
    role = payload_factory.role(retry_max=5)
    env = build_env(include_task=False, role_payload=role)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.0.0"),
        role_id="role.coder_backend",
    )

    assert result.rejection is not None
    assert result.rejection.max_retries == 5


def test_rejection_max_retries_falls_back_to_default(build_env) -> None:
    env = build_env(include_task=False, include_role=False)

    result = env["validator"].input_gate(
        state=env["state"],
        task_ref=ContractRef(id="task.user_auth.login_api", version="1.0.0"),
        role_id="role.coder_backend",
    )

    assert result.rejection is not None
    assert result.rejection.max_retries == 3

