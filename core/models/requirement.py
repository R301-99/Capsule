from __future__ import annotations

from enum import Enum

from pydantic import Field

from .base import StrictModel


class DecisionStatus(str, Enum):
    OPEN = "open"
    PROPOSED = "proposed"
    LOCKED = "locked"


class RequirementStatus(str, Enum):
    ANALYZING = "analyzing"
    FILLING = "filling"
    READY = "ready"
    IMPLEMENTING = "implementing"
    ANALYZING_FAILED = "analyzing_failed"


class DecisionOption(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class DecisionPoint(StrictModel):
    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: list[DecisionOption] = Field(default_factory=list)
    default: str | None = None
    answer: str | None = None
    status: DecisionStatus
    locked_at: str | None = None
    generates_constraints: list[str] = Field(default_factory=list)


class RequirementCategory(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    decision_points: list[DecisionPoint] = Field(default_factory=list)


class RequirementSpec(StrictModel):
    project_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    categories: list[RequirementCategory] = Field(default_factory=list)
    status: RequirementStatus
    created_at: str
    updated_at: str
