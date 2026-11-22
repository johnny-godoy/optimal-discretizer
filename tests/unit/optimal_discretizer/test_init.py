"""Tests for the package."""

import pytest
from beartype.roar import BeartypeCallHintViolation

import optimal_discretizer
from optimal_discretizer.domain.summary import summarize


def test_package_docstring() -> None:
    assert optimal_discretizer.__doc__


def test_version_is_the_installed_version() -> None:
    assert optimal_discretizer.__version__


def test_functions_check_their_argument_types() -> None:
    with pytest.raises(BeartypeCallHintViolation):
        summarize("not numbers")  # pyrefly: ignore[bad-argument-type] -- the call must break the hint to prove the check runs


def test_int_satisfies_a_float_hint() -> None:
    assert summarize([1, 2]).count == 2
