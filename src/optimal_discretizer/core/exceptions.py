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
