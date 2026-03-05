from __future__ import annotations

from core.cli import main


def test_status_on_initialized_project(initialized_project, capsys) -> None:
    code = main(["status", "--root", str(initialized_project)])

    out = capsys.readouterr().out
    assert code == 0
    assert "Project:" in out
    assert "Status:" in out
