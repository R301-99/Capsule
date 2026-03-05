from __future__ import annotations

from pydantic import Field, model_validator

from .base import StrictModel


class WorkflowNode(StrictModel):
    id: str
    role: str
    action: str
    human_review: bool = False


class WorkflowDef(StrictModel):
    id: str
    nodes: list[WorkflowNode] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_node_ids_unique(self) -> "WorkflowDef":
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"Duplicate workflow node id: {node.id}")
            seen.add(node.id)
        return self

