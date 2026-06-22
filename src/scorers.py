"""Implement base scorers for use in OptimalDiscretizer when n_bins=None."""

from typing import Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt


@runtime_checkable
class ScorerProtocol(Protocol):
    """Protocol for scorer functions used in OptimalDiscretizer when n_bins=None."""

    def __call__(
        self,
        x: npt.ArrayLike,
        labels: npt.ArrayLike,
        centroids: npt.ArrayLike,
        n_bins: int,
        inertia: float,
    ) -> float:
        """Compute a score for the given clustering.

        Parameters
        ----------
        x : array-like of shape (n_samples,)
            The original data that was clustered.
        labels : array-like of shape (n_samples,)
            Cluster labels for each sample, as returned by the clustering algorithm.
        centroids : array-like of shape (n_bins,)
            Centroid values for each cluster, as returned by the clustering algorithm.
        n_bins : int
            The number of clusters (bins) used in the clustering.
        inertia : float
            The inertia (sum of squared distances to centroids) of the clustering.

        Returns
        -------
        score : float
            A scalar score indicating the quality of the clustering. Higher is better.
        """


def second_difference_scorer(
    x: npt.ArrayLike,
    labels: npt.ArrayLike,
    centroids: npt.ArrayLike,
    n_bins: int,
    inertia: float,
) -> float:
    """Compute the second-difference score for the given clustering.

    The second-difference score is defined as the difference in inertia between
    the current number of bins and the previous number of bins, minus the
    difference in inertia between the previous number of bins and the one before
    that. Formally:

        score(n_bins) = (inertia(n_bins - 1) - inertia(n_bins)) - (inertia(n_bins - 2) - inertia(n_bins - 1))

    This score captures the "elbow" in the inertia curve, which can indicate an optimal number of clusters.

    Parameters
    ----------
    x : array-like of shape (n_samples,)
        The original data that was clustered.
    labels : array-like of shape (n_samples,)
        Cluster labels for each sample, as returned by the clustering algorithm.
    centroids : array-like of shape (n_bins,)
        Centroid values for each cluster, as returned by the clustering algorithm.
    n_bins : int
        The number of clusters (bins) used in the clustering.
    inertia : float
        The inertia (sum of squared distances to centroids) of the clustering.

    Returns
    -------
    score : float
        The second-difference score for the given clustering. Higher is better.
    """
    if n_bins < 3:  # noqa: PLR2004
        # Not enough bins to compute second difference
        return -np.inf

    # Compute inertia for n_bins - 1 and n_bins - 2
    inertia_n_minus_1 = inertia + np.sum((x - centroids[labels]) ** 2) / n_bins
    inertia_n_minus_2 = inertia_n_minus_1 + np.sum((x - centroids[labels]) ** 2) / (n_bins - 1)

    score = (inertia_n_minus_1 - inertia) - (inertia_n_minus_2 - inertia_n_minus_1)
    return float(score)


SCORER_REGISTRY: dict[str, ScorerProtocol] = {
    "second_difference": second_difference_scorer,
}
