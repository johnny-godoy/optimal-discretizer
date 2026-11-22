"""Tests for the errors."""

import pytest

from optimal_discretizer.core.exceptions import (
    BinCountWarning,
    EmptyInputError,
    InputShapeError,
    NonFiniteValueError,
    OptimalDiscretizerError,
    ParameterRangeError,
    ScorerError,
)


def test_empty_input_error_names_the_input() -> None:
    assert str(EmptyInputError(name="items")) == "items is empty, but it must have at least one item"


def test_non_finite_value_error_names_the_input_and_the_count() -> None:
    assert str(NonFiniteValueError(name="values", count=2)) == (
        "values holds 2 value(s) that are NaN or infinite; remove or impute them before clustering"
    )


def test_input_shape_error_names_the_dimensions() -> None:
    assert str(InputShapeError(name="values", expected=1, actual=2)) == "values must have 1 dimension(s), got 2"


def test_parameter_range_error_names_the_range() -> None:
    assert str(ParameterRangeError(name="n_bins", value=0, allowed="at least 1")) == "n_bins must be at least 1, got 0"


@pytest.mark.parametrize(
    "error",
    [
        EmptyInputError(name="items"),
        NonFiniteValueError(name="values", count=1),
        InputShapeError(name="values", expected=1, actual=2),
        ParameterRangeError(name="n_bins", value=0, allowed="at least 1"),
        ScorerError("unknown scorer"),
    ],
)
def test_every_error_is_a_value_error_of_the_package(error: OptimalDiscretizerError) -> None:
    assert isinstance(error, OptimalDiscretizerError)
    assert isinstance(error, ValueError)


def test_bin_count_warning_is_a_user_warning() -> None:
    assert issubclass(BinCountWarning, UserWarning)
