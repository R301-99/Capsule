from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .base import StrictModel


class ConstraintSource(str, Enum):
    USER_DESCRIPTION = "user_description"
    USER_DECISION = "user_decision"
    USER_ADDITION = "user_addition"
    TEST_PASS = "test_pass"
    FAILURE_LESSON = "failure_lesson"
    INTERFACE_LOCK = "interface_lock"
    SYSTEM_DEFAULT = "system_default"


class ConstraintTypeKind(str, Enum):
    MUST = "must"
    MUST_NOT = "must_not"


class ConstraintEnforcement(str, Enum):
    TEST = "test"
    POLICY = "policy"
    INFO = "info"


class Constraint(StrictModel):
    id: str = Field(pattern=r"^C-\d+$")
    content: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source: ConstraintSource
    source_detail: str | None = None
    constraint_type: ConstraintTypeKind
    enforcement: ConstraintEnforcement
    test_ids: list[str] = Field(default_factory=list)
    frozen: bool = True
    created_at: str

    @model_validator(mode="after")
    def validate_enforcement_consistency(self) -> "Constraint":
        if self.enforcement == ConstraintEnforcement.TEST and not self.test_ids:
            raise ValueError("test_ids must not be empty when enforcement='test'")
        return self
