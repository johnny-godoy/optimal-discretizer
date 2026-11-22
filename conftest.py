"""Give pytest the collection hook of the documentation examples, and let beartype see the editable install.

pytest calls the ``pytest_collect_file`` hook of a ``conftest.py`` only for the files below that ``conftest.py``. The
examples are in ``README.md``, ``docs/`` and ``src/``, so the hook must be in the root ``conftest.py``.
``tests/docs/conftest.py`` holds the configuration.

beartype checks only the modules that the standard path finder loads, and the editable install of meson-python loads
the package with its own finder. ``prefer_source_tree`` lets the path finder load the Python modules from ``src``
before any test imports the package. In a test of a built wheel, it changes nothing.
"""

from pathlib import Path

from scripts.editable_imports import prefer_source_tree

prefer_source_tree(Path(__file__).resolve().parent / "src")

from tests.docs.conftest import pytest_collect_file  # ruff: ignore[module-import-not-at-top-of-file] -- the finders must be in order before any import of the package

__all__ = ["pytest_collect_file"]
