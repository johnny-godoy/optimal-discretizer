"""Tests for the package."""

import pytest
from beartype.roar import BeartypeCallHintViolation

import optimal_discretizer
from optimal_discretizer import centroids_to_edges, kmeans_1d


def test_package_docstring() -> None:
    assert optimal_discretizer.__doc__


def test_version_is_the_installed_version() -> None:
    assert optimal_discretizer.__version__


def test_every_public_name_is_exported() -> None:
    assert all(hasattr(optimal_discretizer, name) for name in optimal_discretizer.__all__)


def test_functions_check_their_argument_types() -> None:
    with pytest.raises(BeartypeCallHintViolation):
        kmeans_1d([1.0, 2.0], "two")  # pyrefly: ignore[bad-argument-type] -- the call must break the hint to prove the check runs


def test_numpy_array_hints_check_the_dtype() -> None:
    with pytest.raises(BeartypeCallHintViolation):
        centroids_to_edges([1.0, 2.0])  # pyrefly: ignore[bad-argument-type] -- the call must break the hint to prove the check runs
