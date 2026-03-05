from __future__ import annotations

from core.cli import main


def test_validate_passes_on_valid_project(initialized_project) -> None:
    code = main(["validate", "--root", str(initialized_project)])
    assert code == 0


def test_validate_fails_without_capsule_yaml(tmp_path) -> None:
    code = main(["validate", "--root", str(tmp_path)])
    assert code == 1
