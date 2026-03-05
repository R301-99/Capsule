from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import ValidationError

from .executor.codex_cli import CodexCliExecutor
from .human_loop import HumanLoop
from .models.base import ContractRef
from .models.config import CapsuleConfig
from .orchestrator import Orchestrator, OrchestratorResult
from .scaffold import ScaffoldReport, scaffold_project
from .state_manager import StateLoadError, StateManager
from .test_runner import TestRunner
from .validate_project import ValidationIssue, validate_project
from .validator import Validator
from .registry import Registry


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_HALTED = 2
EXIT_UNEXPECTED = 3
EXIT_INTERRUPTED = 130


@dataclass(frozen=True)
class Runtime:
    root: Path
    config: CapsuleConfig
    registry: Registry
    state_manager: StateManager
    validator: Validator
    test_runner: TestRunner
    orchestrator: Orchestrator
    human_loop: HumanLoop


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - top-level safety net
        print(f"Unexpected error: {exc}", file=sys.stderr)
        print("Run 'capsule validate' to check project health.", file=sys.stderr)
        return EXIT_UNEXPECTED


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capsule",
        description="Capsule CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p_init = subparsers.add_parser(
        "init",
        help="Initialize a Capsule project",
        description=(
            "Initialize a new Capsule project.\n\n"
            "Creates roles, workflows, contracts, boundaries, schemas, prompts, and state directory."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  capsule init\n"
            "  capsule init --project-id my-app\n"
            "  capsule init --root /path/to/project"
        ),
    )
    p_init.add_argument("--project-id", dest="project_id")
    p_init.add_argument("--root", default=".")

    p_validate = subparsers.add_parser(
        "validate",
        help="Validate project structure, contracts, workflow, and state",
        description="Validate project health with actionable hints.",
    )
    p_validate.add_argument("--root", default=".")

    p_run = subparsers.add_parser(
        "run",
        help="Run workflow for a task",
        description="Execute workflow for a task reference.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  capsule run --task \"task.user_auth.login_api@1.0.0\"\n"
            "  capsule run --task \"task.user_auth.login_api@1.x\""
        ),
    )
    p_run.add_argument("--task", required=True)
    p_run.add_argument("--root", default=".")

    p_review = subparsers.add_parser("review", help="Show pending human review items")
    p_review.add_argument("--root", default=".")

    p_decide = subparsers.add_parser(
        "decide",
        help="Record a human decision for a pending item",
        description=(
            "Make a decision on a pending human review item.\n\n"
            "Option can be provided by name or 1-based index."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  capsule decide --item hq-20260303-101530-ab12cd01 --option approve\n"
            "  capsule decide --item hq-20260303-101530-ab12cd01 --option 1\n"
            "  capsule decide --item hq-20260303-101530-ab12cd01 --option 2 --rationale \"Needs rework\""
        ),
    )
    p_decide.add_argument("--item", required=True)
    p_decide.add_argument("--option", required=True)
    p_decide.add_argument("--rationale", default="")
    p_decide.add_argument("--root", default=".")

    p_resume = subparsers.add_parser("resume", help="Resume workflow after human decisions")
    p_resume.add_argument("--root", default=".")

    p_status = subparsers.add_parser("status", help="Show current project status")
    p_status.add_argument("--root", default=".")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "review":
        return _cmd_review(args)
    if args.command == "decide":
        return _cmd_decide(args)
    if args.command == "resume":
        return _cmd_resume(args)
    if args.command == "status":
        return _cmd_status(args)
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return EXIT_ERROR


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    project_id = _resolve_project_id(root, args.project_id)
    report = scaffold_project(root, project_id)
    _print_scaffold_report(report)

    conventions: dict[str, Any] = {}
    try:
        config, _ = _load_config(root)
        conventions = dict(config.global_conventions)
    except Exception:
        conventions = {}

    state_manager = StateManager(root / "state")
    _ensure_state_layout(state_manager)
    if state_manager.project_state_path.exists():
        print("State already initialized; keeping existing PROJECT_STATE.json.")
    else:
        state_manager.init_project(project_id, conventions)
        print(f"Project '{project_id}' initialized.")

    if report.errors:
        print(f"Scaffold completed with {len(report.errors)} errors.", file=sys.stderr)
        return EXIT_ERROR

    print("")
    print(f"Project '{project_id}' ready.")
    print("Next steps:")
    print("  1. Add your task contracts to contracts/instances/<module>/")
    print("  2. Run 'capsule validate' to check everything")
    print("  3. Run 'capsule run --task \"task.<module>.<name>@1.0.0\"' to start")
    return EXIT_OK


def _cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    issues = validate_project(root)
    _print_validation_report(issues)
    errors = [issue for issue in issues if issue.level == "error"]
    return EXIT_ERROR if errors else EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    issues = validate_project(root)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        if any("PROJECT_STATE.json" in issue.message for issue in errors):
            print("Project is not initialized. Run 'capsule init' first.", file=sys.stderr)
        else:
            print("Project has errors. Run 'capsule validate' for details.", file=sys.stderr)
        return EXIT_ERROR

    try:
        task_ref = parse_task_ref(args.task)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    try:
        runtime = _build_runtime(root, on_event=_cli_event_printer)
        workflow = runtime.orchestrator.load_workflow(runtime.root / runtime.config.workflow)
        result = runtime.orchestrator.run(workflow, task_ref)
    except StateLoadError:
        print("Project state not found. Run 'capsule init' first.", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    return _render_orchestrator_result(result, runtime.human_loop, runtime.state_manager)


def _cmd_review(args: argparse.Namespace) -> int:
    try:
        runtime = _build_runtime(Path(args.root).resolve())
        state = runtime.state_manager.load()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    reviews = runtime.human_loop.get_pending_reviews(state)
    if not reviews:
        print("No pending reviews.")
        return EXIT_OK

    for review in reviews:
        print(runtime.human_loop.format_review(review))
        print("")
    return EXIT_OK


def _cmd_decide(args: argparse.Namespace) -> int:
    try:
        runtime = _build_runtime(Path(args.root).resolve())
        state = runtime.state_manager.load()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    try:
        state = runtime.human_loop.apply_decision(state, args.item, args.option, args.rationale)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    runtime.state_manager.save(state)
    print(f"Decision recorded: {args.option} for {args.item}")

    if not runtime.state_manager.pending_human_items(state):
        print("All reviews resolved. Run 'capsule resume' to continue.")
    return EXIT_OK


def _cmd_resume(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    issues = validate_project(root)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        print("Project has errors. Run 'capsule validate' for details.", file=sys.stderr)
        return EXIT_ERROR

    try:
        runtime = _build_runtime(root, on_event=_cli_event_printer)
        workflow = runtime.orchestrator.load_workflow(runtime.root / runtime.config.workflow)
        result = runtime.orchestrator.resume(workflow)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    return _render_orchestrator_result(result, runtime.human_loop, runtime.state_manager)


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        runtime = _build_runtime(Path(args.root).resolve())
        state = runtime.state_manager.load()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    run_total = len(state.run_history)
    passed = len([run for run in state.run_history if run.status.value == "passed"])
    waiting = len([run for run in state.run_history if run.status.value == "waiting_human"])
    pending_human = len(runtime.state_manager.pending_human_items(state))
    task_ref = (
        f"{state.current_task_ref.id}@{state.current_task_ref.version}"
        if state.current_task_ref is not None
        else "None"
    )

    print(f"Project:    {state.project_id}")
    print(f"Status:     {state.status.value}")
    print(f"Workflow:   {state.current_workflow_id}")
    print(f"Node:       {state.current_node_id}")
    print(f"Task:       {task_ref}")
    if run_total == 0:
        print("Runs:       No runs yet")
    else:
        print(f"Runs:       {run_total} total ({passed} passed, {waiting} waiting_human)")
    print(f"Human Queue: {pending_human} pending")
    return EXIT_OK


def parse_task_ref(value: str) -> ContractRef:
    text = value.strip()
    if "@" not in text:
        raise ValueError(
            f"Invalid --task '{value}'. Expected format: task.<module>.<name>@<version> (example: task.user_auth.login_api@1.0.0)"
        )
    contract_id, version = text.split("@", 1)
    contract_id = contract_id.strip()
    version = version.strip()
    if not contract_id or not version:
        raise ValueError(
            f"Invalid --task '{value}'. Expected format: task.<module>.<name>@<version> (example: task.user_auth.login_api@1.0.0)"
        )
    if not contract_id.startswith("task."):
        raise ValueError(f"Invalid task contract id '{contract_id}'. It must start with 'task.'")
    return ContractRef(id=contract_id, version=version)


def _render_orchestrator_result(result: OrchestratorResult, human_loop: HumanLoop, state_manager: StateManager) -> int:
    print(f"Status: {result.status}")
    print(f"Runs executed: {result.runs_executed}")
    if result.status == "completed":
        print(f"Workflow completed. {result.runs_executed} runs executed.")
        return EXIT_OK
    if result.status == "waiting_human":
        state = state_manager.load()
        reviews = human_loop.get_pending_reviews(state)
        if reviews:
            print("")
            print("Workflow paused. Pending reviews:")
            for review in reviews:
                print(human_loop.format_review(review))
                print("")
        print("Run 'capsule review' for details and 'capsule decide --item <ID> --option <OPTION>' to proceed.")
        return EXIT_OK
    if result.status == "halted":
        state = state_manager.load()
        reviews = human_loop.get_pending_reviews(state)
        if reviews:
            print("")
            print("Workflow halted. Boundary-related reviews:")
            for review in reviews:
                print(human_loop.format_review(review))
                print("")
        print("Run 'capsule review' to inspect violations.")
        return EXIT_HALTED
    if result.status == "error":
        if result.error_message:
            print(result.error_message, file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


def _load_config(root: Path) -> tuple[CapsuleConfig, Path]:
    config_path = root / "capsule.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"capsule.yaml not found in {root}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid capsule.yaml at {config_path}")
    payload = raw.get("capsule", raw)
    try:
        config = CapsuleConfig(**payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid capsule config: {exc}") from exc
    return config, config_path


def _build_runtime(root: Path, on_event: Callable[[str, dict[str, Any]], None] | None = None) -> Runtime:
    config, config_path = _load_config(root)
    project_root = config_path.parent
    registry = Registry.build(project_root)
    state_manager = StateManager(project_root / "state")
    validator = Validator(registry, state_manager)
    executor = _build_executor(config)
    test_runner = TestRunner(timeout_seconds=config.test_runner.timeout_seconds)
    orchestrator = Orchestrator(
        registry=registry,
        state_manager=state_manager,
        validator=validator,
        executor=executor,
        test_runner=test_runner,
        project_root=project_root,
        on_event=on_event,
    )
    human_loop = HumanLoop(state_manager)
    return Runtime(
        root=project_root,
        config=config,
        registry=registry,
        state_manager=state_manager,
        validator=validator,
        test_runner=test_runner,
        orchestrator=orchestrator,
        human_loop=human_loop,
    )


def _build_executor(config: CapsuleConfig):
    executor_type = config.executor.type.strip().lower()
    if executor_type != "codex_cli":
        raise ValueError(f"Unsupported executor type: {config.executor.type}")
    return CodexCliExecutor(
        codex_command=config.executor.codex_command,
        default_timeout=config.executor.timeout_seconds,
    )


def _resolve_project_id(root: Path, cli_project_id: str | None) -> str:
    if cli_project_id and cli_project_id.strip():
        return cli_project_id.strip()
    config_path = root / "capsule.yaml"
    if config_path.exists():
        try:
            config, _ = _load_config(root)
            return config.project_id
        except Exception:
            pass
    return root.name or "capsule-project"


def _ensure_state_layout(state_manager: StateManager) -> None:
    state_manager.runs_dir.mkdir(parents=True, exist_ok=True)
    state_manager.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    state_manager.audit_dir.mkdir(parents=True, exist_ok=True)
    state_manager.boundary_log_path.touch(exist_ok=True)


def _print_scaffold_report(report: ScaffoldReport) -> None:
    for path in report.created:
        print(f"  [create] {path}")
    for path in report.skipped:
        print(f"  [skip]   {path} (already exists)")
    for message in report.errors:
        print(f"  [error]  {message}", file=sys.stderr)


def _print_validation_report(issues: list[ValidationIssue]) -> None:
    grouped: dict[str, list[ValidationIssue]] = {
        "structure": [],
        "contract": [],
        "workflow": [],
        "state": [],
    }
    for issue in issues:
        grouped.setdefault(issue.category, []).append(issue)

    print("Capsule Project Validation")
    print("==========================")
    for category in ("structure", "contract", "workflow", "state"):
        print("")
        print(category.capitalize())
        category_issues = grouped.get(category, [])
        if not category_issues:
            print("  OK")
            continue
        for issue in category_issues:
            prefix = "ERROR" if issue.level == "error" else "WARN"
            print(f"  {prefix}: {issue.message}")
            print(f"    Fix: {issue.fix_hint}")

    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]
    print("")
    if errors:
        print(f"Result: {len(errors)} errors, {len(warnings)} warnings")
    else:
        print(f"Result: ALL CHECKS PASSED ({len(warnings)} warnings)")


def _cli_event_printer(event_type: str, data: dict[str, Any]) -> None:
    if event_type == "node_start":
        print(f"Node: {data.get('node_id')}")
        return
    if event_type == "input_gate":
        status = "passed" if data.get("passed") else "failed"
        refs = data.get("refs_count", 0)
        print(f"  INPUT GATE: {status} ({refs} refs locked)")
        return
    if event_type == "executing":
        retry = data.get("retry", 0)
        print(f"  EXECUTING (attempt {retry + 1}) ...")
        return
    if event_type == "execution_done":
        status = "ok" if data.get("success") else "failed"
        duration_ms = data.get("duration_ms")
        print(f"  EXECUTION DONE: {status} ({duration_ms}ms)")
        return
    if event_type == "output_gate_level":
        level = data.get("level")
        result = data.get("result")
        print(f"  OUTPUT GATE L{level}: {result}")
        l2 = data.get("l2")
        if isinstance(l2, dict) and l2.get("status") is not None:
            print(f"    L2: {l2.get('status')} ({l2.get('summary', '')})")
        return
    if event_type == "node_passed":
        print("  NODE PASSED")
        return
    if event_type == "node_failed":
        retry = data.get("retry")
        level = data.get("level")
        print(f"  NODE FAILED at level {level}; retry={retry}")
        return
    if event_type == "breaker":
        print(f"  RETRY BREAKER triggered after {data.get('retries')} retries")
        return
    if event_type == "human_gate":
        print(f"  HUMAN REVIEW REQUIRED ({data.get('trigger')})")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
