"""Tests for the import-linter runner that reads the package from src."""

from pathlib import Path

import pytest
from scripts import lint_imports


def test_main_reorders_the_finders_then_runs_import_linter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def prefer(source: Path) -> bool:
        calls.append(f"prefer {source.name}")
        return True

    def lint(args: list[str], standalone_mode: bool) -> None:  # ruff: ignore[boolean-type-hint-positional-argument] -- the keyword of the click command that the script calls
        calls.append(f"lint {args} {standalone_mode}")

    monkeypatch.setattr(lint_imports, "prefer_source_tree", prefer)
    monkeypatch.setattr(lint_imports, "lint_imports_command", lint)
    lint_imports.main()
    assert calls == ["prefer src", "lint [] True"]


def test_the_root_is_the_repository() -> None:
    assert (lint_imports.ROOT / "pyproject.toml").is_file()
    assert Path(__file__).resolve().parents[3] == lint_imports.ROOT
