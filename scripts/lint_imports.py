"""Run import-linter on the package in ``src``, also in a meson-python editable install.

import-linter finds the files of the package from the location that the import system reports. The editable install
of meson-python reports a virtual path, so this script first lets the path finder load the package from ``src``
(``scripts/editable_imports.py``), then runs ``lint-imports`` with the contracts of ``pyproject.toml``.

Run it from the repo root: ``uv run python -m scripts.lint_imports``. The import-linter hook of ``prek.toml`` runs it.
"""

import sys
from pathlib import Path

from importlinter.cli import lint_imports_command

from scripts.editable_imports import prefer_source_tree

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Reorder the finders, then run import-linter, which exits with its own status."""
    prefer_source_tree(ROOT / "src")
    lint_imports_command(args=[], standalone_mode=True)


if __name__ == "__main__":
    sys.exit(main())
