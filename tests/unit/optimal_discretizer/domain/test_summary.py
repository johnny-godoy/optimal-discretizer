"""Tests for the summary statistics."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from optimal_discretizer.core.exceptions import EmptyInputError
from optimal_discretizer.domain.summary import Summary, summarize

FINITE: st.SearchStrategy[float] = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)


def test_summarize_returns_every_statistic() -> None:
    assert summarize([3.0, 1.0, 2.0]) == Summary(count=3, minimum=1.0, maximum=3.0, mean=2.0)


def test_summarize_of_one_value() -> None:
    assert summarize([5.0]) == Summary(count=1, minimum=5.0, maximum=5.0, mean=5.0)


def test_summarize_rejects_an_empty_sequence() -> None:
    with pytest.raises(EmptyInputError, match="values is empty"):
        summarize([])


@given(st.lists(FINITE, min_size=1))
def test_mean_lies_between_the_minimum_and_the_maximum(values: list[float]) -> None:
    summary = summarize(values)
    assert summary.minimum <= summary.mean or math.isclose(summary.minimum, summary.mean)
    assert summary.mean <= summary.maximum or math.isclose(summary.mean, summary.maximum)
