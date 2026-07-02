"""Implement base scorers for use in OptimalDiscretizer when n_bins=None."""

from collections.abc import Sequence
from typing import ClassVar, NamedTuple, Protocol, runtime_checkable
import warnings

from kneed import KneeLocator
import numpy as np
import numpy.typing as npt


class CandidateFit(NamedTuple):
    """Immutable clustering result for one candidate number of bins."""

    n_bins: int
    labels: np.ndarray
    centroids: np.ndarray
    inertia: float


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


class CurveScorerProtocol(Protocol):
    """Protocol for scorers that choose directly from the full candidate sweep."""

    is_curve_scorer: ClassVar[bool]

    def __call__(self, x: npt.ArrayLike, candidates: Sequence[CandidateFit]) -> int:
        """Choose the best number of bins from the evaluated candidate fits.

        Parameters
        ----------
        x : array-like of shape (n_samples,)
            The original data that was clustered.
        candidates : sequence of CandidateFit
            Evaluated candidate clusterings sorted by increasing ``n_bins``.

        Returns
        -------
        n_bins : int
            The selected number of bins.
        """


def _resolve_min_std(x: npt.ArrayLike, min_std: float | None) -> float:
    """Resolve the minimum residual standard deviation used for MDL coding."""

    if min_std is not None:
        min_std_float = float(min_std)
        if min_std_float <= 0:
            msg = f"min_std must be > 0, got {min_std_float}"
            raise ValueError(msg)
        return min_std_float

    x_array = np.asarray(x, dtype=np.float64)
    unique_values = np.unique(x_array)
    if unique_values.size < 2:
        return float(np.finfo(np.float64).eps)

    gaps = np.diff(unique_values)
    positive_gaps = gaps[gaps > 0]
    if positive_gaps.size == 0:
        return float(np.finfo(np.float64).eps)

    return float(0.5 * positive_gaps.min())


def _mdl_terms(
    x: npt.ArrayLike,
    labels: npt.ArrayLike,
    centroids: npt.ArrayLike,
    n_bins: int,
    min_std: float | None = None,
) -> tuple[float, float]:
    """Compute model and residual code lengths, in bits, for a clustering."""

    x_array = np.asarray(x, dtype=np.float64)
    labels_array = np.asarray(labels, dtype=np.intp)
    centroids_array = np.asarray(centroids, dtype=np.float64)

    n_samples = x_array.shape[0]
    min_std_resolved = _resolve_min_std(x_array, min_std)
    floor_var = min_std_resolved**2

    residuals = x_array - centroids_array[labels_array]
    counts = np.bincount(labels_array, minlength=n_bins)
    squared_residual_sums = np.bincount(labels_array, weights=np.square(residuals), minlength=n_bins)

    variances = np.full(n_bins, floor_var, dtype=np.float64)
    nonempty_bins = counts > 0
    variances[nonempty_bins] = np.maximum(squared_residual_sums[nonempty_bins] / counts[nonempty_bins], floor_var)

    entropy_bits = 0.5 * np.log2(2.0 * np.pi * np.e * variances[nonempty_bins])
    data_bits = float(np.sum(counts[nonempty_bins] * entropy_bits))
    model_bits = float(n_bins * 0.5 * np.log2(n_samples) + np.log2(n_bins))
    return model_bits, data_bits


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


def mdl_gaussian_scorer(
    x: npt.ArrayLike,
    labels: npt.ArrayLike,
    centroids: npt.ArrayLike,
    n_bins: int,
    inertia: float,  # noqa: ARG001
    min_std: float | None = None,
) -> float:
    """Compute a Gaussian MDL score for the given clustering.

    The score is the negative of a two-part minimum-description-length code:

    ``total_bits(n_bins) = L(model) + L(data | model)``

    with

    ``L(model) = n_bins * 0.5 * log2(n_samples) + log2(n_bins)``

    and

    ``L(data | model) = sum_j n_j * 0.5 * log2(2 * pi * e * var_j)``

    where ``var_j`` is the biased within-bin residual variance for bin ``j``.
    Residual variances are floored at ``min_std**2``. When ``min_std`` is
    ``None``, it is inferred from the data as half of the smallest non-zero gap
    between adjacent sorted unique values, which treats the observed data
    resolution as the finest encodable precision.

    The Gaussian residual term is a conservative coding estimate: among all
    distributions with a fixed variance, the Gaussian has the largest
    differential entropy. Scoring each bin's residuals with the Gaussian entropy
    therefore does not understate the number of bits needed to encode them. With
    the maximum-likelihood residual variance, the average negative Gaussian
    log-likelihood equals the closed-form entropy expression above, so no
    separate likelihood evaluation is required.

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
    min_std : float or None, default=None
        Minimum residual standard deviation used to floor per-bin variances.
        When ``None``, the floor is inferred from the observed data precision.

    Returns
    -------
    score : float
        The negative total code length in bits. Higher is better.
    """
    model_bits, data_bits = _mdl_terms(x=x, labels=labels, centroids=centroids, n_bins=n_bins, min_std=min_std)
    return -(model_bits + data_bits)


class MDLBitsKneeScorer:
    """Select ``n_bins`` from the knee of the MDL bit-space trade-off curve.

    This scorer evaluates the parametric curve whose horizontal axis is
    ``L(model)`` and whose vertical axis is ``L(data | model)``. The curve is an
    MDL analogue of the L-curve criterion used in regularization: model
    complexity rises as fit residual bits fall, and the knee marks a balance
    between those competing costs. Knee detection is delegated to
    :class:`kneed.KneeLocator`, which implements the Kneedle algorithm described
    by Satopää, Albrecht, Irwin, and Raghavan (ICDCSW 2011) for discrete
    monotone curves by normalizing them and locating prominent deviations from
    the endpoint diagonal.

    If no knee is detected, the scorer falls back to the candidate that directly
    minimizes ``L(model) + L(data | model)``, which matches
    :func:`mdl_gaussian_scorer`, and emits a :class:`UserWarning`.

    Parameters
    ----------
    min_std : float or None, default=None
        Minimum residual standard deviation forwarded to :func:`_mdl_terms`.
    **kneed_kwargs
        Additional keyword arguments forwarded to :class:`kneed.KneeLocator`.
        Defaults to ``curve="convex"`` and ``direction="decreasing"`` for the
        bit-space trade-off curve used here.
    """

    is_curve_scorer: ClassVar[bool] = True

    def __init__(self, min_std: float | None = None, **kneed_kwargs: object) -> None:
        self.min_std = min_std
        self.kneed_kwargs = {"curve": "convex", "direction": "decreasing", **kneed_kwargs}

    def __call__(self, x: npt.ArrayLike, candidates: Sequence[CandidateFit]) -> int:
        """Choose ``n_bins`` from the knee of the MDL bit-space curve.

        Parameters
        ----------
        x : array-like of shape (n_samples,)
            The original data that was clustered.
        candidates : sequence of CandidateFit
            Evaluated candidate clusterings sorted by increasing ``n_bins``.

        Returns
        -------
        n_bins : int
            The selected number of bins.

        Warns
        -----
        UserWarning
            If ``KneeLocator`` does not find a knee and the scorer falls back to
            minimizing total MDL code length directly.
        """
        model_bits = np.empty(len(candidates), dtype=np.float64)
        data_bits = np.empty(len(candidates), dtype=np.float64)

        for index, candidate in enumerate(candidates):
            model_bits[index], data_bits[index] = _mdl_terms(
                x=x,
                labels=candidate.labels,
                centroids=candidate.centroids,
                n_bins=candidate.n_bins,
                min_std=self.min_std,
            )

        locator = KneeLocator(model_bits, data_bits, **self.kneed_kwargs)
        if locator.knee is None:
            total_bits = model_bits + data_bits
            fallback_index = int(np.argmin(total_bits))
            fallback_n_bins = candidates[fallback_index].n_bins
            warnings.warn(
                "KneeLocator did not find an MDL bits knee; falling back to the minimum total MDL code length.",
                UserWarning,
                stacklevel=2,
            )
            return fallback_n_bins

        knee_index = int(np.argmin(np.abs(model_bits - float(locator.knee))))
        return candidates[knee_index].n_bins


class KneedInertiaScorer:
    """Select ``n_bins`` from the knee of the ``(n_bins, inertia)`` curve.

    This scorer applies :class:`kneed.KneeLocator` directly to the inertia sweep
    over evaluated candidates. It uses the same discrete-knee heuristic from the
    Kneedle algorithm of Satopää, Albrecht, Irwin, and Raghavan (ICDCSW 2011),
    but in the original elbow-style coordinate system rather than the MDL
    bit-space curve.

    If no knee is detected, the scorer falls back to the smallest evaluated
    ``n_bins`` and emits a :class:`UserWarning`.

    Parameters
    ----------
    **kneed_kwargs
        Additional keyword arguments forwarded to :class:`kneed.KneeLocator`.
        Defaults to ``curve="convex"`` and ``direction="decreasing"`` for the
        monotone decreasing inertia curve used here.
    """

    is_curve_scorer: ClassVar[bool] = True

    def __init__(self, **kneed_kwargs: object) -> None:
        self.kneed_kwargs = {"curve": "convex", "direction": "decreasing", **kneed_kwargs}

    def __call__(self, x: npt.ArrayLike, candidates: Sequence[CandidateFit]) -> int:  # noqa: ARG002
        """Choose ``n_bins`` from the knee of the inertia curve.

        Parameters
        ----------
        x : array-like of shape (n_samples,)
            The original data that was clustered.
        candidates : sequence of CandidateFit
            Evaluated candidate clusterings sorted by increasing ``n_bins``.

        Returns
        -------
        n_bins : int
            The selected number of bins.

        Warns
        -----
        UserWarning
            If ``KneeLocator`` does not find an inertia knee and the scorer
            falls back to the smallest evaluated ``n_bins``.
        """
        n_bins_array = np.array([candidate.n_bins for candidate in candidates], dtype=np.float64)
        inertia_array = np.array([candidate.inertia for candidate in candidates], dtype=np.float64)

        locator = KneeLocator(n_bins_array, inertia_array, **self.kneed_kwargs)
        if locator.knee is None:
            fallback_n_bins = candidates[0].n_bins
            warnings.warn(
                "KneeLocator did not find an inertia knee; falling back to the smallest evaluated n_bins.",
                UserWarning,
                stacklevel=2,
            )
            return fallback_n_bins

        knee_index = int(np.argmin(np.abs(n_bins_array - float(locator.knee))))
        return candidates[knee_index].n_bins


SCORER_REGISTRY: dict[str, ScorerProtocol] = {
    "second_difference": second_difference_scorer,
    "mdl_gaussian": mdl_gaussian_scorer,
}

CURVE_SCORER_REGISTRY: dict[str, CurveScorerProtocol] = {
    "mdl_bits_knee": MDLBitsKneeScorer(),
    "kneed_inertia": KneedInertiaScorer(),
}
