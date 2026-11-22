"""Tests for the errors."""

from optimal_discretizer.core.exceptions import EmptyInputError, OptimalDiscretizerError


def test_empty_input_error_names_the_input() -> None:
    assert str(EmptyInputError(name="items")) == "items is empty, but it must have at least one item"


def test_empty_input_error_is_a_value_error_of_the_package() -> None:
    error = EmptyInputError(name="items")
    assert isinstance(error, OptimalDiscretizerError)
    assert isinstance(error, ValueError)
