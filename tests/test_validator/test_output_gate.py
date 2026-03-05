from __future__ import annotations

from core.models.base import ContractRef
from core.models.enums import GateLevel, GateResult


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


def _valid_evidence(run_id: str, task_ref: ContractRef, snapshot_refs: list[ContractRef]) -> dict:
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


def test_output_gate_passes_for_valid_payload(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.passed is True
    assert result.halt is False
    assert result.rejection is None
    assert result.gate_report["result"] == GateResult.PASS
    assert result.gate_report["level"] == GateLevel.L3
    assert result.gate_report["diagnostics"]["details"]["l2"]["status"] == "skipped"
    assert result.l2_result is not None
    assert result.l2_result["status"] == "skipped"


def test_output_gate_fails_l0_when_evidence_invalid(build_env) -> None:
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
    assert result.halt is False
    assert result.rejection is not None
    assert result.gate_report["level"] == GateLevel.L0


def test_output_gate_fails_l1_when_task_ref_mismatch(build_env) -> None:
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
    assert result.halt is False
    assert result.rejection is not None
    assert result.gate_report["level"] == GateLevel.L1


def test_output_gate_fails_l1_when_locked_refs_missing(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)
    evidence = _valid_evidence(run.run_id, run.task_ref, locked_refs[:-1])

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=evidence,
        modified_files=["src/backend/auth.py"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.passed is False
    assert result.halt is False
    assert result.rejection is not None
    assert result.gate_report["level"] == GateLevel.L1


def test_output_gate_halts_on_sacred_file_violation(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["contracts/schemas/foo.json"],
        commands_ran=["pytest -q tests/backend/test_auth.py"],
    )

    assert result.passed is False
    assert result.halt is True
    assert result.rejection is None
    assert result.gate_report["result"] == GateResult.HALT
    assert result.gate_report["level"] == GateLevel.L3
    assert result.boundary_violations


def test_output_gate_halts_on_prohibited_command(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["git push origin main"],
    )

    assert result.passed is False
    assert result.halt is True
    assert any("prohibited" in item.lower() for item in result.boundary_violations)


def test_output_gate_halts_on_unauthorized_command(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["src/backend/auth.py"],
        commands_ran=["npm run build"],
    )

    assert result.passed is False
    assert result.halt is True
    assert any("outside role capabilities" in item.lower() for item in result.boundary_violations)


def test_output_gate_collects_multiple_boundary_violations(build_env) -> None:
    env = build_env()
    state, run, locked_refs = _prepare_run(env)

    result = env["validator"].output_gate(
        state=state,
        run_id=run.run_id,
        evidence=_valid_evidence(run.run_id, run.task_ref, locked_refs),
        modified_files=["contracts/schemas/foo.json"],
        commands_ran=["git push origin main", "npm run build"],
    )

    assert result.passed is False
    assert result.halt is True
    assert len(result.boundary_violations) >= 3
    assert result.gate_report["diagnostics"]["details"]["l2"]["status"] == "skipped"
