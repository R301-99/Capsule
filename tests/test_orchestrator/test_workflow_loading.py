from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError


def test_load_workflow_parses_valid_yaml(build_orchestrator) -> None:
    env = build_orchestrator()
    workflow_path = env["project_root"] / "workflows" / "single.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "workflow": {
                    "id": "workflow.single",
                    "nodes": [
                        {
                            "id": "coder_backend",
                            "role": "role.coder_backend",
                            "action": "implement",
                        }
                    ],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    workflow = env["orchestrator"].load_workflow(workflow_path)

    assert workflow.id == "workflow.single"
    assert len(workflow.nodes) == 1


def test_load_workflow_missing_nodes_fails(build_orchestrator) -> None:
    env = build_orchestrator()
    workflow_path = env["project_root"] / "workflows" / "broken.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(yaml.safe_dump({"workflow": {"id": "workflow.broken"}}), encoding="utf-8")

    with pytest.raises(ValidationError):
        env["orchestrator"].load_workflow(workflow_path)


def test_load_workflow_missing_required_node_field_fails(build_orchestrator) -> None:
    env = build_orchestrator()
    workflow_path = env["project_root"] / "workflows" / "invalid_node.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "workflow": {
                    "id": "workflow.invalid",
                    "nodes": [
                        {
                            "id": "coder_backend",
                            "action": "implement",
                        }
                    ],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        env["orchestrator"].load_workflow(workflow_path)
