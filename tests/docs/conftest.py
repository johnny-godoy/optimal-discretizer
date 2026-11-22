"""Run the code examples of the documentation as tests, with Sybil.

The examples are in two places, and the site shows both. The ``Examples`` sections of the docstrings in
``src/optimal_discretizer`` are doctests, and the API reference page shows them. The ``python`` code blocks of
``README.md`` and ``docs/*.md`` run in order, and the code blocks of one file share their variables. The root
``conftest.py`` gives the collection hook of this file to pytest, because a collection hook works only for the files
below its ``conftest.py``.

Run the examples with ``just test-docs``. Put setup that the reader does not need in an
``<!-- invisible-code-block: python -->`` comment, and skip a block with ``<!-- skip: next -- <reason> -->``.
"""

import doctest  # ruff: ignore[banned-api] -- Sybil reads the option flags of doctest; the project runs no doctest itself
from collections.abc import Callable
from pathlib import Path

import pytest
from sybil import Sybil
from sybil.parsers.markdown import PythonCodeBlockParser, SkipParser
from sybil.parsers.rest import DocTestParser

ROOT: Path = Path(__file__).resolve().parents[2]
# the doctests compare the text of the output, so a reflowed long repr must still match
OPTIONS: int = doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE

MARKDOWN: Sybil = Sybil(
    parsers=[PythonCodeBlockParser(doctest_optionflags=OPTIONS), SkipParser()],
    path=str(ROOT),
    patterns=["README.md", "docs/*.md"],
    name="markdown",
)
DOCSTRINGS: Sybil = Sybil(
    parsers=[DocTestParser(optionflags=OPTIONS)],
    path=str(ROOT),
    # "**/" needs one directory at least, so the modules at the top of the package need a pattern of their own
    patterns=["src/optimal_discretizer/*.py", "src/optimal_discretizer/**/*.py"],
    name="docstrings",
)

pytest_collect_file: Callable[[Path, pytest.Collector], pytest.Collector | None] = (MARKDOWN + DOCSTRINGS).pytest()
