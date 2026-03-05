from __future__ import annotations

from core.models.base import ContractRef
from core.models.evidence import CommandRecord, ExecutionEvidenceSpec
from core.models.execution import ExecutionRequest, ExecutionResult
from core.models.enums import TestSummary
from core.test_runner import TestResult


def build_evidence(
    request: ExecutionRequest,
    result: ExecutionResult,
    resolved_refs: list[ContractRef],
    test_result: TestResult | None = None,
) -> dict:
    notes = (result.agent_output or "")[:500]
    if test_result is not None:
        tests_ran = [
            CommandRecord(
                cmd=test_result.command,
                exit_code=test_result.exit_code,
                duration_ms=test_result.duration_ms,
            )
        ]
        tests_summary = TestSummary.PASS if test_result.passed else TestSummary.FAIL
    else:
        tests_ran = []
        tests_summary = TestSummary.PASS if result.success else TestSummary.FAIL

    evidence = ExecutionEvidenceSpec(
        run_id=request.run_id,
        role_id=request.role_id,
        task_ref=request.task_ref,
        contract_snapshot={"refs": resolved_refs},
        changes={
            "modified_files": result.modified_files,
            "diff_stat": {
                "files": len(result.modified_files),
                "insertions": 0,
                "deletions": 0,
            },
        },
        commands={
            "ran": [
                CommandRecord(
                    cmd=cmd.cmd,
                    exit_code=cmd.exit_code,
                    duration_ms=cmd.duration_ms,
                )
                for cmd in result.commands_ran
            ]
        },
        tests={
            "ran": tests_ran,
            "summary": tests_summary,
        },
        self_report={
            "confidence": 0.5,
            "risks": [],
            "notes": notes,
        },
    )
    return evidence.model_dump(mode="json")
