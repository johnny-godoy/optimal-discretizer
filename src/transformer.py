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

import warnings
from collections.abc import Callable
from typing import Self

import numpy as np
import numpy.typing as npt
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted, validate_data

from src._core import cluster as _cluster_core
from src.utils import centroids_to_edges


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
    n_bins : int or None, default=5
        Number of clusters / bins to produce per feature column.
        When ``None``, the estimator searches over ``[n_bins_min, n_bins_max]`` and
        picks the value that maximises ``scorer`` for each feature.
    n_bins_range : tuple[int, int] or None, default=None
        Inclusive search range used only when ``n_bins=None``.
        If ``None``, defaults to ``(1, n_samples)`` during :meth:`fit`.
    scorer : Callable or None, default=None
        Scoring function used only when ``n_bins=None``. The function is called as
        ``scorer(x=..., labels=..., centroids=..., n_bins=..., inertia=...)`` and
        must return a scalar score to maximise.

    Attributes
    ----------
    centroids_ : list of ndarray of shape (n_bins_j,)
        Centroid of each bin for every input feature, ordered by cluster index.
        Available after :meth:`fit`.
    bin_edges_ : list of ndarray of shape (n_bins_j + 1,)
        Bin-edge thresholds derived from centroids.  Each threshold is the
        midpoint between consecutive centroids.  Available after :meth:`fit`.
    n_bins_ : list of int
        Selected number of bins per feature. Equals ``n_bins`` for all features
        when ``n_bins`` is provided.
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

    def __init__(
        self,
        n_bins: int | None = 5,
        n_bins_range: tuple[int, int] | None = None,
        scorer: Callable[..., float] | None = None,
    ) -> None:
        self.n_bins = n_bins
        self.n_bins_range = n_bins_range
        self.scorer = scorer

    def _check_fit_params(self, n_samples: int) -> None:
        """Validate constructor parameters that depend on sample count.

        Raises
        ------
        ValueError
            If ``n_bins`` is outside ``[1, n_samples]`` or ``n_bins_range`` is invalid.
        """
        if self.n_bins is not None:
            n_bins = int(self.n_bins)
            if n_bins < 1:
                msg = f"n_bins must be >= 1, got {n_bins}"
                raise ValueError(msg)
            if n_bins > n_samples:
                msg = f"n_bins must be <= n_samples, got n_samples={n_samples} and n_bins={n_bins}"
                raise ValueError(msg)

        if self.n_bins_range is not None:
            if len(self.n_bins_range) != 2:  # noqa: PLR2004
                msg = f"n_bins_range must be a tuple of length 2, got {self.n_bins_range!r}"
                raise ValueError(msg)
            n_bins_min, n_bins_max = self.n_bins_range
            n_bins_min = int(n_bins_min)
            n_bins_max = int(n_bins_max)
            if n_bins_min < 1:
                msg = f"n_bins_min must be >= 1, got {n_bins_min}"
                raise ValueError(msg)
            if n_bins_max > n_samples:
                msg = f"n_bins_max must be <= n_samples, got n_samples={n_samples} and n_bins_max={n_bins_max}"
                raise ValueError(msg)
            if n_bins_min > n_bins_max:
                msg = f"n_bins_min must be <= n_bins_max, got n_bins_min={n_bins_min} and n_bins_max={n_bins_max}"
                raise ValueError(msg)

    def _resolve_n_bins_bounds(self, n_samples: int) -> tuple[int, int]:
        if self.n_bins_range is None:
            return (1, n_samples)
        n_bins_min, n_bins_max = self.n_bins_range
        return (int(n_bins_min), int(n_bins_max))

    def _score(
        self,
        x: np.ndarray,
        labels: np.ndarray,
        centroids: np.ndarray,
        n_bins: int,
        inertia: float,
    ) -> float:
        scorer = self.scorer
        if scorer is None:
            msg = "scorer must be provided when n_bins is None"
            raise ValueError(msg)
        score = scorer(x=x, labels=labels, centroids=centroids, n_bins=n_bins, inertia=inertia)
        return float(score)

    def _select_n_bins_for_column(self, col_data: np.ndarray, n_samples: int) -> tuple[np.ndarray, np.ndarray, int]:
        if self.n_bins is not None:
            n_bins = int(self.n_bins)
            labels, centroids = _cluster_core(col_data, n_bins)
            return labels, centroids, n_bins

        if self.scorer is None:
            warnings.warn(
                "Both n_bins and scorer are None. Falling back to n_bins=1.",
                UserWarning,
                stacklevel=2,
            )
            labels, centroids = _cluster_core(col_data, 1)
            return labels, centroids, 1

        n_bins_min, n_bins_max = self._resolve_n_bins_bounds(n_samples)

        best_score = -np.inf
        best_labels: np.ndarray | None = None
        best_centroids: np.ndarray | None = None
        best_n_bins = n_bins_min

        for n_bins_candidate in range(n_bins_min, n_bins_max + 1):
            labels, centroids = _cluster_core(col_data, n_bins_candidate)
            residuals = col_data - centroids[labels]
            inertia = float(np.square(residuals).sum())
            score = self._score(col_data, labels, centroids, n_bins_candidate, inertia)
            if score > best_score:
                best_score = score
                best_labels = labels
                best_centroids = centroids
                best_n_bins = n_bins_candidate

        if best_labels is None or best_centroids is None:
            msg = "Failed to select n_bins from search range"
            raise RuntimeError(msg)

        return best_labels, best_centroids, best_n_bins

    def fit(
        self,
        X: npt.ArrayLike,
        y: None = None,  # noqa: ARG002
    ) -> Self:
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
        self._check_fit_params(n_samples)

        self.centroids_: list[np.ndarray] = []
        self.bin_edges_: list[np.ndarray] = []
        self.n_bins_: list[int] = []

        for col in range(n_features):
            col_data = np.ascontiguousarray(X[:, col], dtype=np.float64)
            _, centroids, selected_n_bins = self._select_n_bins_for_column(col_data, n_samples)
            self.centroids_.append(centroids)
            edges = centroids_to_edges(centroids)
            self.bin_edges_.append(edges)
            self.n_bins_.append(selected_n_bins)

        return self

    def transform(self, X: npt.ArrayLike) -> np.ndarray:
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
            # np.searchsorted with 'right' gives bin indices in [1, n_bins_j];
            # subtract 1 to get 0-indexed labels.
            labels = np.searchsorted(edges[1:-1], X[:, col], side="right")
            out[:, col] = labels

        return out
