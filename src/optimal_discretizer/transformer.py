"""
Scikit-learn compatible transformer for optimal 1-D k-means discretization.

This module wraps the Cython ``cluster`` function from ``_core`` in a
:class:`sklearn.base.TransformerMixin` / :class:`sklearn.base.BaseEstimator`
interface so it can be used as a drop-in step inside a
:class:`sklearn.pipeline.Pipeline`.

References
----------
Gronlund, A., Larsen, K. G., Mathiasen, A., Nielsen, J. S., Schneider, S., & Song, M. (2017).
*Fast Exact k-Means, k-Medians and Bregman Divergence Clustering in 1D*.
https://arxiv.org/abs/1701.07204
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted, validate_data

from ._core import cluster as _cluster_core


class OptimalDiscretizer(TransformerMixin, BaseEstimator):
    """Optimal 1-D K-means discretizer.

    Partitions each feature column independently into *n_bins* clusters whose
    assignment minimises the total within-cluster sum of squares (the exact
    global optimum for 1-D data).

    The fitted transformer replaces each value with its cluster label
    (an integer in ``[0, n_bins - 1]``).  Labels are ordered so that cluster 0
    contains the smallest values and cluster ``n_bins - 1`` contains the
    largest.

    Parameters
    ----------
    n_bins : int, default=5
        Number of clusters / bins to produce per feature column.

    Attributes
    ----------
    centroids_ : list of ndarray of shape (n_bins,)
        Centroid of each bin for every input feature, ordered by cluster index.
        Available after :meth:`fit`.
    bin_edges_ : list of ndarray of shape (n_bins + 1,)
        Bin-edge thresholds derived from centroids.  Each threshold is the
        midpoint between consecutive centroids.  Available after :meth:`fit`.
    n_features_in_ : int
        Number of features seen during :meth:`fit`.

    Examples
    --------
    >>> import numpy as np
    >>> from optimal_discretizer import OptimalDiscretizer
    >>> rng = np.random.default_rng(0)
    >>> X = rng.normal(size=(100, 2))
    >>> disc = OptimalDiscretizer(n_bins=3)
    >>> disc.fit_transform(X).shape
    (100, 2)
    """

    def __init__(self, n_bins: int = 5) -> None:
        self.n_bins = n_bins

    # ------------------------------------------------------------------
    # Scikit-learn estimator interface
    # ------------------------------------------------------------------

    def fit(self, X, y=None):
        """Fit the discretizer on *X*.

        For each feature column the optimal 1-D k-means solution is computed
        and the resulting centroids and bin edges are stored.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features) or (n_samples,)
            Training data.
        y : ignored

        Returns
        -------
        self : OptimalDiscretizer
        """
        X = validate_data(self, X, ensure_2d=True, dtype=np.float64)

        n_samples, n_features = X.shape
        n_bins = int(self.n_bins)
        if n_bins < 1:
            raise ValueError(f"n_bins must be >= 1, got {n_bins}")
        if n_bins > n_samples:
            raise ValueError(
                f"n_bins must be <= n_samples, got n_samples={n_samples} and n_bins={n_bins}"
            )

        self.centroids_: list[np.ndarray] = []
        self.bin_edges_: list[np.ndarray] = []

        for col in range(n_features):
            col_data = np.ascontiguousarray(X[:, col], dtype=np.float64)
            _, centroids = _cluster_core(col_data, n_bins)
            self.centroids_.append(centroids)
            edges = self._centroids_to_edges(centroids)
            self.bin_edges_.append(edges)

        return self

    def transform(self, X):
        """Discretize *X* using the fitted bin edges.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features) or (n_samples,)
            Data to discretize.

        Returns
        -------
        X_disc : ndarray of shape (n_samples, n_features), dtype int64
            Cluster label (0-indexed) for each element.
        """
        check_is_fitted(self)
        X = validate_data(self, X, ensure_2d=True, dtype=np.float64, reset=False)

        n_features = X.shape[1]

        out = np.empty_like(X, dtype=np.float64)
        for col in range(n_features):
            edges = self.bin_edges_[col]
            # np.searchsorted with 'right' gives bin indices in [1, n_bins];
            # subtract 1 to get 0-indexed labels and clip to [0, n_bins-1].
            labels = np.searchsorted(edges[1:-1], X[:, col], side="right")
            out[:, col] = labels

        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _centroids_to_edges(centroids: np.ndarray) -> np.ndarray:
        """Convert sorted centroid array to bin-edge thresholds.

        Edges are midpoints between consecutive centroids, with ``-inf`` and
        ``+inf`` as the outermost sentinels.
        """
        mid = (centroids[:-1] + centroids[1:]) / 2.0
        return np.concatenate([[-np.inf], mid, [np.inf]])
