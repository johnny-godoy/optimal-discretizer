"""Tests of exact 1-D k-means.

The Lean proof in ``proofs/`` covers a model of the kernel in exact arithmetic. The differential tests below link that
model to the compiled code: they compare ``kmeans_1d`` with a plain O(k * n^2) dynamic program and, for small inputs,
with a search over every contiguous partition.
"""

import itertools
import time
import tracemalloc

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from optimal_discretizer.domain.optimal_partition import optimal_starts

from optimal_discretizer.core.exceptions import (
    EmptyInputError,
    InputShapeError,
    NonFiniteValueError,
    ParameterRangeError,
)
from optimal_discretizer.domain.clustering import kmeans_1d

# The wheel tests of cibuildwheel run without the conftest files, so the tests set their own timing: a slow or emulated
# runner must not fail on time.
_NO_DEADLINE = settings(deadline=None)
# Inputs with many equal values, to exercise the ties of SMAWK.
_TIED_VALUES = st.lists(st.integers(min_value=-3, max_value=3).map(float), min_size=1, max_size=40)
_SPREAD_VALUES = st.lists(
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=40,
)


def reference_inertia(values: npt.NDArray[np.float64], cluster_count: int) -> float:
    """Return the smallest inertia of a contiguous partition, by the plain O(k * n^2) dynamic program.

    The program reads the interval costs from direct sums, not from prefix sums, so it shares no arithmetic with the
    kernel.

    Returns
    -------
    float
        The smallest total squared error.

    """
    sorted_values = np.sort(values)
    value_count = sorted_values.size

    def interval_cost(first: int, last: int) -> float:
        interval = sorted_values[first : last + 1]
        return float(np.square(interval - interval.mean()).sum())

    costs = [interval_cost(0, last) for last in range(value_count)]
    for layer in range(1, cluster_count):
        costs = [
            min(
                (costs[first - 1] + interval_cost(first, last) for first in range(layer, last + 1)),
                default=np.inf,
            )
            for last in range(value_count)
        ]
    return costs[value_count - 1]


def brute_force_inertia(values: npt.NDArray[np.float64], cluster_count: int) -> float:
    """Return the smallest inertia over every assignment of the values to ``cluster_count`` non-empty clusters.

    The search does not assume that a cluster is contiguous, so it checks the contiguity claim too.

    Returns
    -------
    float
        The smallest total squared error.

    """
    best = np.inf
    for assignment in itertools.product(range(cluster_count), repeat=values.size):
        labels = np.array(assignment)
        if np.unique(labels).size != cluster_count:
            continue
        inertia = sum(
            float(np.square(values[labels == cluster] - values[labels == cluster].mean()).sum())
            for cluster in range(cluster_count)
        )
        best = min(best, inertia)
    return best


def assert_valid_clustering(values: npt.NDArray[np.float64], cluster_count: int) -> float:
    """Check the structure of the result of ``kmeans_1d`` and return its inertia.

    Returns
    -------
    float
        The inertia of the result.

    """
    clustering = kmeans_1d(values, cluster_count)
    assert clustering.labels.shape == values.shape
    assert clustering.centroids.shape == (cluster_count,)
    assert set(clustering.labels.tolist()) == set(range(cluster_count))
    for cluster in range(cluster_count):
        members = values[clustering.labels == cluster]
        assert clustering.centroids[cluster] == pytest.approx(members.mean(), abs=1e-9)
    assert np.all(np.diff(clustering.centroids) >= 0)
    order = np.argsort(values, kind="stable")
    assert np.all(np.diff(clustering.labels[order]) >= 0), "the clusters must be runs of the sorted values"
    assert clustering.inertia == pytest.approx(float(np.square(values - clustering.centroids[clustering.labels]).sum()))
    return clustering.inertia


@_NO_DEADLINE
@given(values=st.one_of(_TIED_VALUES, _SPREAD_VALUES), data=st.data())
def test_kmeans_1d_matches_the_plain_dynamic_program(values: list[float], data: st.DataObject) -> None:
    array = np.array(values)
    cluster_count = data.draw(st.integers(min_value=1, max_value=array.size), label="cluster_count")
    inertia = assert_valid_clustering(array, cluster_count)
    expected = reference_inertia(array, cluster_count)
    scale = max(1.0, float(np.square(array - array.mean()).sum()))
    assert inertia == pytest.approx(expected, rel=1e-9, abs=1e-9 * scale)


@_NO_DEADLINE
@given(values=st.lists(st.integers(min_value=-2, max_value=4).map(float), min_size=1, max_size=7), data=st.data())
def test_kmeans_1d_matches_a_search_over_every_clustering(values: list[float], data: st.DataObject) -> None:
    array = np.array(values)
    cluster_count = data.draw(st.integers(min_value=1, max_value=min(array.size, 3)), label="cluster_count")
    assert kmeans_1d(array, cluster_count).inertia == pytest.approx(brute_force_inertia(array, cluster_count), abs=1e-9)


@_NO_DEADLINE
@given(values=st.one_of(_TIED_VALUES, _SPREAD_VALUES))
def test_one_cluster_holds_every_value(values: list[float]) -> None:
    array = np.array(values)
    clustering = kmeans_1d(array, 1)
    assert clustering.labels.tolist() == [0] * array.size
    assert clustering.centroids[0] == pytest.approx(array.mean())


@_NO_DEADLINE
@given(values=st.one_of(_TIED_VALUES, _SPREAD_VALUES))
def test_one_cluster_for_each_value_has_no_error(values: list[float]) -> None:
    array = np.array(values)
    clustering = kmeans_1d(array, array.size)
    assert sorted(clustering.labels.tolist()) == list(range(array.size))
    assert clustering.inertia == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("cluster_count", [1, 2, 5, 6])
def test_constant_values_give_clusters_with_the_constant_as_centroid(cluster_count: int) -> None:
    clustering = kmeans_1d(np.full(6, 5.0), cluster_count)
    assert clustering.centroids.tolist() == [5.0] * cluster_count
    assert clustering.inertia == pytest.approx(0.0, abs=1e-12)


def test_more_clusters_than_distinct_values_gives_sorted_centroids_and_no_empty_cluster() -> None:
    # Guard: the first kernel allowed empty clusters and left their centroids uninitialized (5e-324, unsorted).
    clustering = kmeans_1d(np.array([3.0, 3.0, 0.0, 0.0]), 3)
    assert clustering.centroids.tolist() == [0.0, 0.0, 3.0]
    assert sorted(set(clustering.labels.tolist())) == [0, 1, 2]


def test_two_groups_are_separated() -> None:
    clustering = kmeans_1d(np.array([10.0, 1.0, 11.0, 2.0]), 2)
    assert clustering.labels.tolist() == [1, 0, 1, 0]
    assert clustering.centroids.tolist() == [1.5, 10.5]
    assert clustering.inertia == pytest.approx(1.0)


def test_a_single_sample_is_its_own_cluster() -> None:
    clustering = kmeans_1d([4.25], 1)
    assert clustering.labels.tolist() == [0]
    assert clustering.centroids.tolist() == [4.25]
    assert clustering.inertia == pytest.approx(0.0, abs=1e-12)


def test_integer_input_is_converted() -> None:
    assert kmeans_1d([1, 2, 30], 2).centroids.tolist() == [1.5, 30.0]


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_a_value_that_is_not_finite_is_rejected(bad_value: float) -> None:
    with pytest.raises(NonFiniteValueError, match="1 value"):
        kmeans_1d([1.0, bad_value, 3.0], 2)


def test_two_dimensional_input_is_rejected() -> None:
    with pytest.raises(InputShapeError, match="must have 1 dimension"):
        kmeans_1d([[1.0, 2.0]], 1)


def test_empty_input_is_rejected() -> None:
    with pytest.raises(EmptyInputError, match="values is empty"):
        kmeans_1d([], 1)


@pytest.mark.parametrize("cluster_count", [0, 4])
def test_a_cluster_count_outside_one_to_n_is_rejected(cluster_count: int) -> None:
    with pytest.raises(ParameterRangeError, match="between 1 and 3"):
        kmeans_1d([1.0, 2.0, 3.0], cluster_count)


@pytest.mark.parametrize("interval_count", [0, 4])
def test_the_kernel_rejects_an_interval_count_outside_one_to_n(interval_count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and the number of values"):
        optimal_starts(np.array([1.0, 2.0, 3.0]), np.empty(interval_count, dtype=np.intp))


def test_the_kernel_returns_the_cost_of_itsoptimal_partition() -> None:
    starts = np.empty(2, dtype=np.intp)
    total_cost = optimal_starts(np.array([1.0, 2.0, 10.0, 11.0]), starts)
    assert starts.tolist() == [0, 2]
    assert total_cost == pytest.approx(1.0)


def test_large_input_runs_in_linear_time_and_memory_per_cluster() -> None:
    sample_count, cluster_count = 1_000_000, 8
    values = np.random.default_rng(0).normal(size=sample_count)
    tracemalloc.start()
    started = time.perf_counter()
    clustering = kmeans_1d(values, cluster_count)
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert np.all(np.diff(clustering.centroids) > 0)
    # The kernel holds k * n indices and 8 * n numbers; the wrapper holds a few arrays of n values.
    assert peak_bytes < (cluster_count + 20) * 8 * sample_count
    # About 0.5 s on a laptop. The bound is wide, because shared CI runners are slow and noisy.
    assert elapsed < 30.0
