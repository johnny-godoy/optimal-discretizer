"""The errors of ``optimal_discretizer``.

Every error that ``optimal_discretizer`` raises on purpose derives from ``OptimalDiscretizerError``, so
``except OptimalDiscretizerError`` catches all of them. An error for a bad value also derives from ``ValueError``.
"""


class OptimalDiscretizerError(Exception):
    """The base class of the errors that ``optimal_discretizer`` raises."""


class EmptyInputError(OptimalDiscretizerError, ValueError):
    """An input is empty, but the operation needs at least one item."""

    def __init__(self, name: str) -> None:
        """Build the message from the name of the input.

        Parameters
        ----------
        name: str
            The name of the empty input.

        """
        super().__init__(f"{name} is empty, but it must have at least one item")


class NonFiniteValueError(OptimalDiscretizerError, ValueError):
    """An input holds NaN or an infinite value, but the operation needs finite numbers."""

    def __init__(self, name: str, count: int) -> None:
        """Build the message from the name of the input and the number of values that are not finite.

        Parameters
        ----------
        name: str
            The name of the input.
        count: int
            The number of NaN and infinite values in the input.

        """
        super().__init__(
            f"{name} holds {count} value(s) that are NaN or infinite; remove or impute them before clustering",
        )


class InputShapeError(OptimalDiscretizerError, ValueError):
    """An input has the wrong number of dimensions."""

    def __init__(self, name: str, expected: int, actual: int) -> None:
        """Build the message from the name of the input and its dimensions.

        Parameters
        ----------
        name: str
            The name of the input.
        expected: int
            The number of dimensions that the operation needs.
        actual: int
            The number of dimensions of the input.

        """
        super().__init__(f"{name} must have {expected} dimension(s), got {actual}")


class ParameterRangeError(OptimalDiscretizerError, ValueError):
    """A parameter is outside the range of values that the operation accepts."""

    def __init__(self, name: str, value: float, allowed: str) -> None:
        """Build the message from the name of the parameter, its value and the allowed range.

        Parameters
        ----------
        name: str
            The name of the parameter.
        value: float
            The value that was given.
        allowed: str
            The allowed range, in words, for example ``"between 1 and 10"``.

        """
        super().__init__(f"{name} must be {allowed}, got {value}")


class ScorerError(OptimalDiscretizerError, ValueError):
    """A scorer is unknown, missing, or gave a result that the discretizer cannot use."""


class BinCountWarning(UserWarning):
    """A feature has fewer distinct values than the number of bins, so the discretizer uses fewer bins."""
