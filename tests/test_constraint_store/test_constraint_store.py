from __future__ import annotations

from core.constraint_store import ConstraintStore
from core.models.constraint import Constraint


def _constraint(
    *,
    constraint_id: str,
    content: str,
    category: str,
    source: str,
    enforcement: str,
    test_ids: list[str] | None = None,
) -> Constraint:
    return Constraint(
        id=constraint_id,
        content=content,
        category=category,
        source=source,
        constraint_type="must",
        enforcement=enforcement,
        test_ids=test_ids or [],
        frozen=True,
        created_at="2026-01-01T00:00:00Z",
    )


def test_add_and_query(tmp_path) -> None:
    store = ConstraintStore(tmp_path)
    c1 = _constraint(
        constraint_id="C-001",
        content="Use Python",
        category="architecture",
        source="user_description",
        enforcement="policy",
    )
    c2 = _constraint(
        constraint_id="C-002",
        content="Wall collision ends game",
        category="behavior",
        source="user_decision",
        enforcement="test",
        test_ids=["test_wall_collision"],
    )
    constraints = store.add_batch([c1, c2])
    store.save(constraints)

    loaded = store.load()
    assert len(loaded) == 2

    test_constraints = store.get_test_constraints()
    assert len(test_constraints) == 1
    assert test_constraints[0].id == "C-002"
    assert store.count() == 2


def test_roundtrip(tmp_path) -> None:
    store = ConstraintStore(tmp_path)
    c1 = _constraint(
        constraint_id="C-001",
        content="x",
        category="misc",
        source="user_description",
        enforcement="info",
    )
    store.save(store.add(c1))

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].content == "x"


def test_duplicate_ids_are_renumbered(tmp_path) -> None:
    store = ConstraintStore(tmp_path)
    c1 = _constraint(
        constraint_id="C-001",
        content="first",
        category="architecture",
        source="user_description",
        enforcement="policy",
    )
    c2 = _constraint(
        constraint_id="C-001",
        content="second",
        category="behavior",
        source="user_decision",
        enforcement="test",
        test_ids=["test_second"],
    )

    constraints = store.add_batch([c1, c2])
    assert constraints[0].id == "C-001"
    assert constraints[1].id == "C-002"
