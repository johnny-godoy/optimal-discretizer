"""Shared kernel: the errors and the types that every other layer of ``optimal_discretizer`` may import."""

from optimal_discretizer.core.exceptions import (
    BinCountWarning,
    EmptyInputError,
    InputShapeError,
    NonFiniteValueError,
    OptimalDiscretizerError,
    ParameterRangeError,
    ScorerError,
)

__all__ = [
    "BinCountWarning",
    "EmptyInputError",
    "InputShapeError",
    "NonFiniteValueError",
    "OptimalDiscretizerError",
    "ParameterRangeError",
    "ScorerError",
]
