from __future__ import annotations

import yaml

from core.cli import main
from core.state_manager import StateManager


def _set_review_workflow(project_root):
    review_path = project_root / "workflows" / "review.yaml"
    review_path.write_text(
        yaml.safe_dump(
            {
                "workflow": {
                    "id": "workflow.review",
                    "nodes": [
                        {
                            "id": "coder_backend",
                            "role": "role.coder_backend",
                            "action": "implement",
                            "human_review": True,
                        }
                    ],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_root / "capsule.yaml").write_text(
        "capsule:\n"
        "  project_id: test-project\n"
        "  workflow: workflows/review.yaml\n"
        "  executor:\n"
        "    type: codex_cli\n"
        "    codex_command: codex\n"
        "    timeout_seconds: 300\n"
        "  test_runner:\n"
        "    timeout_seconds: 120\n",
        encoding="utf-8",
    )


def test_resume_fails_with_unresolved_human_items(initialized_project, patch_cli_runtime) -> None:
    patch_cli_runtime()
    _set_review_workflow(initialized_project)

    code_run = main(["run", "--task", "task.user_auth.login_api@1.0.0", "--root", str(initialized_project)])
    assert code_run == 0

    state = StateManager(initialized_project / "state").load()
    assert len(state.human_queue) > 0

    code_resume = main(["resume", "--root", str(initialized_project)])
    assert code_resume == 1


def test_resume_completes_after_decisions_resolved(initialized_project, patch_cli_runtime) -> None:
    patch_cli_runtime()
    _set_review_workflow(initialized_project)

    code_run = main(["run", "--task", "task.user_auth.login_api@1.0.0", "--root", str(initialized_project)])
    assert code_run == 0

    sm = StateManager(initialized_project / "state")
    state = sm.load()
    for item in sm.pending_human_items(state):
        state = sm.resolve_human(state, item.item_id, "HD-cli-001")
    sm.save(state)

    code_resume = main(["resume", "--root", str(initialized_project)])
    assert code_resume == 0

    state = sm.load()
    assert state.status.value == "completed"
