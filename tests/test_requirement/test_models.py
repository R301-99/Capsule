from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.constraint import Constraint
from core.models.requirement import DecisionPoint, RequirementCategory, RequirementSpec


def test_constraint_creation() -> None:
    constraint = Constraint(
        id="C-001",
        content="Use Python language",
        category="architecture",
        source="user_description",
        constraint_type="must",
        enforcement="policy",
        test_ids=[],
        frozen=True,
        created_at="2026-01-01T00:00:00Z",
    )

    assert constraint.id == "C-001"
    assert constraint.frozen is True


def test_constraint_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Constraint(
            id="C-001",
            content="x",
            category="y",
            source="user_description",
            constraint_type="must",
            enforcement="policy",
            test_ids=[],
            frozen=True,
            created_at="2026-01-01T00:00:00Z",
            unknown_field="bad",
        )


def test_constraint_requires_test_ids_when_enforcement_is_test() -> None:
    with pytest.raises(ValidationError):
        Constraint(
            id="C-002",
            content="Wall collision ends game",
            category="behavior",
            source="user_decision",
            constraint_type="must",
            enforcement="test",
            test_ids=[],
            frozen=True,
            created_at="2026-01-01T00:00:00Z",
        )


def test_decision_point_lifecycle() -> None:
    dp = DecisionPoint(
        id="dp.beh.wall",
        category="behavior",
        question="Wall collision behavior?",
        options=[{"id": "die", "label": "Game over"}, {"id": "wrap", "label": "Wrap around"}],
        default="die",
        answer=None,
        status="proposed",
        locked_at=None,
        generates_constraints=["Wall collision -> {answer}"],
    )

    assert dp.status.value == "proposed"
    assert dp.answer is None


def test_requirement_spec_structure() -> None:
    spec = RequirementSpec(
        project_id="test",
        description="test project",
        categories=[
            RequirementCategory(
                id="behavior",
                name="Behavior",
                decision_points=[],
            )
        ],
        status="analyzing",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    assert spec.status.value == "analyzing"
    assert len(spec.categories) == 1
