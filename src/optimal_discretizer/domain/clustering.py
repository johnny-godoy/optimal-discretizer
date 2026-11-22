"""Exact k-means clustering of one-dimensional data.

``kmeans_1d`` sorts the values, lets the compiled kernel ``optimal_partition.optimal_starts`` find the contiguous
partition with the smallest sum of squared deviations, and maps the partition back to the order of the input. The
kernel follows the dynamic program of Grønlund et al. (2017), "Fast Exact k-Means, k-Medians and Bregman Divergence
Clustering in 1D" (arXiv:1701.07204), with SMAWK for each layer. ``proofs/papers/kmeans-1d/paper.typ`` proves, in
exact arithmetic, that the result is a global minimum of the k-means objective. The proof does not cover floating point.
"""

import attrs
import numpy as np
import numpy.typing as npt

from optimal_discretizer.core.exceptions import (
    EmptyInputError,
    InputShapeError,
    NonFiniteValueError,
    ParameterRangeError,
)
from optimal_discretizer.domain.optimal_partition import optimal_starts


@attrs.frozen
class Clustering1D:
    """The result of ``kmeans_1d``.

    Attributes
    ----------
    labels: numpy.ndarray of int64, shape (n_samples,)
        The cluster of each value, in the order of the input. Cluster 0 holds the smallest values.
    centroids: numpy.ndarray of float64, shape (n_clusters,)
        The mean of each cluster, in increasing order.
    inertia: float
        The sum of squared distances from each value to the centroid of its cluster.

    """

    labels: npt.NDArray[np.int64]
    centroids: npt.NDArray[np.float64]
    inertia: float


def _checked_values(values: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Convert the input to a one-dimensional array of finite float64 values.

    Parameters
    ----------
    values: array-like
        The input of ``kmeans_1d``.

    Returns
    -------
    numpy.ndarray of float64
        The values as a contiguous array.

    Raises
    ------
    InputShapeError
        If the input is not one-dimensional.
    EmptyInputError
        If the input has no values.
    NonFiniteValueError
        If a value is NaN or infinite.

    """
    array = np.ascontiguousarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise InputShapeError(name="values", expected=1, actual=array.ndim)
    if array.size == 0:
        raise EmptyInputError(name="values")
    non_finite_count = int(np.count_nonzero(~np.isfinite(array)))
    if non_finite_count:
        raise NonFiniteValueError(name="values", count=non_finite_count)
    return array


def kmeans_1d(values: npt.ArrayLike, n_clusters: int) -> Clustering1D:
    """Cluster one-dimensional values into exactly ``n_clusters`` non-empty clusters with the smallest inertia.

    Each cluster is a run of consecutive values in sorted order. If the values hold fewer than ``n_clusters`` distinct
    numbers, some clusters hold equal values and have equal centroids, and the inertia is 0.

    Parameters
    ----------
    values: array-like of shape (n_samples,)
        Finite numbers. They need not be sorted.
    n_clusters: int
        The number of clusters, between 1 and ``n_samples``.

    Returns
    -------
    Clustering1D
        The labels in the order of the input, the centroids in increasing order, and the inertia.

    Raises
    ------
    ParameterRangeError
        If ``n_clusters`` is not between 1 and the number of values.

    Examples
    --------
    >>> from optimal_discretizer import kmeans_1d
    >>> clustering = kmeans_1d([1.0, 10.0, 2.0, 11.0], n_clusters=2)
    >>> clustering.labels.tolist()
    [0, 1, 0, 1]
    >>> clustering.centroids.tolist()
    [1.5, 10.5]
    >>> clustering.inertia
    1.0

    """
    array = _checked_values(values)
    sample_count = array.size
    if not 1 <= n_clusters <= sample_count:
        raise ParameterRangeError(name="n_clusters", value=n_clusters, allowed=f"between 1 and {sample_count}")
    order = np.argsort(array, kind="stable")
    sorted_values = array[order]
    starts = np.empty(n_clusters, dtype=np.intp)
    optimal_starts(sorted_values, starts)
    counts = np.diff(starts, append=sample_count)
    centroids = np.add.reduceat(sorted_values, starts) / counts
    labels = np.empty(sample_count, dtype=np.int64)
    labels[order] = np.repeat(np.arange(n_clusters, dtype=np.int64), counts)
    inertia = float(np.square(array - centroids[labels]).sum())
    return Clustering1D(labels=labels, centroids=centroids, inertia=inertia)
