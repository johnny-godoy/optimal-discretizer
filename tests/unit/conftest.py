"""Pytest hooks and Hypothesis settings for all unit tests."""

import os
from pathlib import Path

import orjson
import pytest
from hypothesis import settings
from scripts import mutant_tests

# A random failure in CI is a flaky build that blocks other pull requests, so CI and the mutation runs draw the same
# examples every time and keep no example database. A timing limit fails at random on a slow runner, so it is off.
settings.register_profile("ci", derandomize=True, database=None, deadline=None)
settings.load_profile("ci" if os.environ.get("CI") or os.environ.get("MUTATION_FIRST") else "default")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Run the tests that can kill the mutant first.

    ``scripts/mutation.py`` sets ``MUTATION_FIRST`` to the name of the mutated module, ``MUTATION_MODULE`` to its path,
    ``MUTATION_ORIGINAL`` to the project root with the unmutated source, and ``MUTATION_COVERAGE`` to the coverage map
    of the baseline. The run stops at the first failure, so the tests that execute the mutated statements come first,
    then the other tests of the mutated module, then the rest. Without the variables, the order does not change.
    """
    module = os.environ.get("MUTATION_FIRST")
    if not module:
        return
    covering: set[str] = set()
    path = os.environ.get("MUTATION_MODULE")
    if path and "MUTATION_ORIGINAL" in os.environ and "MUTATION_COVERAGE" in os.environ:
        coverage = orjson.loads(Path(os.environ["MUTATION_COVERAGE"]).read_bytes()).get(path, {})
        original = (Path(os.environ["MUTATION_ORIGINAL"]) / path).read_text()
        covering = mutant_tests.covering_tests(coverage, original, (config.rootpath / path).read_text())
    items.sort(key=lambda item: (item.nodeid not in covering, item.path.stem != f"test_{module}"))
