"""Summary statistics of a sequence of numbers: an example of pure domain logic."""

from collections.abc import Sequence

import attrs

from optimal_discretizer.core.exceptions import EmptyInputError


@attrs.frozen
class Summary:
    """The summary statistics of a sequence of numbers.

    Attributes
    ----------
    count: int
        The number of values.
    minimum: float
        The smallest value.
    maximum: float
        The largest value.
    mean: float
        The arithmetic mean of the values.

    """

    count: int
    minimum: float
    maximum: float
    mean: float


def summarize(values: Sequence[float]) -> Summary:
    """Calculate the summary statistics of a sequence of numbers.

    Parameters
    ----------
    values: Sequence[float]
        The numbers.

    Returns
    -------
    Summary
        The count, the smallest value, the largest value and the mean.

    Raises
    ------
    EmptyInputError
        If ``values`` is empty.

    Examples
    --------
    >>> summarize([1.0, 2.0, 6.0])
    Summary(count=3, minimum=1.0, maximum=6.0, mean=3.0)

    """
    if not values:
        raise EmptyInputError(name="values")
    return Summary(count=len(values), minimum=min(values), maximum=max(values), mean=sum(values) / len(values))
