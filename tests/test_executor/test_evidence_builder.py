from __future__ import annotations

from core.executor.evidence_builder import build_evidence
from core.models.base import ContractRef
from core.models.evidence import ExecutionEvidenceSpec
from core.models.evidence import CommandRecord
from core.models.execution import ExecutionRequest, ExecutionResult
from core.test_runner import TestResult


def test_build_evidence_produces_l0_valid_payload(execution_request: ExecutionRequest) -> None:
    result = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=["src/backend/auth.py"],
        commands_ran=[CommandRecord(cmd="codex exec --json ...", exit_code=0, duration_ms=100)],
        agent_output="all done",
        duration_ms=100,
    )
    refs = [ContractRef(id="task.user_auth.login_api", version="1.0.0")]

    evidence = build_evidence(execution_request, result, refs)

    parsed = ExecutionEvidenceSpec(**evidence)
    assert parsed.run_id == execution_request.run_id
    assert parsed.tests.summary.value == "pass"


def test_build_evidence_handles_failed_result(execution_request: ExecutionRequest) -> None:
    result = ExecutionResult(
        success=False,
        exit_code=1,
        modified_files=[],
        commands_ran=[CommandRecord(cmd="codex exec --json ...", exit_code=1, duration_ms=100)],
        agent_output="failure",
        error_message="non-zero exit",
        duration_ms=100,
    )
    refs = [ContractRef(id="task.user_auth.login_api", version="1.0.0")]

    evidence = build_evidence(execution_request, result, refs)

    parsed = ExecutionEvidenceSpec(**evidence)
    assert parsed.tests.summary.value == "fail"


def test_build_evidence_handles_empty_agent_output(execution_request: ExecutionRequest) -> None:
    result = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=[],
        commands_ran=[CommandRecord(cmd="codex exec --json ...", exit_code=0, duration_ms=100)],
        agent_output="",
        duration_ms=100,
    )
    refs = [ContractRef(id="task.user_auth.login_api", version="1.0.0")]

    evidence = build_evidence(execution_request, result, refs)

    parsed = ExecutionEvidenceSpec(**evidence)
    assert parsed.self_report.notes == ""


def test_build_evidence_uses_test_result_when_provided(execution_request: ExecutionRequest) -> None:
    result = ExecutionResult(
        success=True,
        exit_code=0,
        modified_files=[],
        commands_ran=[CommandRecord(cmd="codex exec --json ...", exit_code=0, duration_ms=100)],
        agent_output="",
        duration_ms=100,
    )
    test_result = TestResult(
        passed=False,
        exit_code=1,
        command="pytest -q tests/backend/test_auth.py",
        stdout="11 passed, 1 failed",
        stderr="FAILED tests/backend/test_auth.py::test_login",
        duration_ms=300,
        summary="11 passed, 1 failed",
        error_details=["FAILED tests/backend/test_auth.py::test_login"],
    )
    refs = [ContractRef(id="task.user_auth.login_api", version="1.0.0")]

    evidence = build_evidence(execution_request, result, refs, test_result=test_result)

    parsed = ExecutionEvidenceSpec(**evidence)
    assert parsed.tests.summary.value == "fail"
    assert len(parsed.tests.ran) == 1
    assert parsed.tests.ran[0].cmd == "pytest -q tests/backend/test_auth.py"
