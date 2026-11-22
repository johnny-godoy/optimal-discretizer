"""Choose the number of bins of a feature from a sweep of exact clusterings.

Each scorer has one method, ``select``, which takes the values of a feature and the clusterings for consecutive
numbers of bins, and returns the number of bins to use. ``OptimalDiscretizer`` calls it when ``n_bins`` is ``None``.

The scorers are heuristics. Each clustering in the sweep is exact for its number of bins, but no scorer claims that
the number of bins it returns is optimal for any purpose.
"""

import warnings
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, Protocol, TypeAlias, runtime_checkable

import attrs
import numpy as np
import numpy.typing as npt
from kneed.knee_locator import KneeLocator

from optimal_discretizer.core.exceptions import ParameterRangeError, ScorerError
from optimal_discretizer.domain.clustering import Clustering1D

_MIN_DISTINCT_VALUES_FOR_GAP = 2
_SECOND_DIFFERENCE_NEIGHBOURS = 3

KneeCurve: TypeAlias = Literal["convex", "concave"]
KneeDirection: TypeAlias = Literal["decreasing", "increasing"]


@attrs.frozen
class CandidateFit:
    """The exact clustering of a feature for one number of bins.

    Attributes
    ----------
    n_bins: int
        The number of bins.
    clustering: Clustering1D
        The labels, the centroids and the inertia of the clustering.

    """

    n_bins: int
    clustering: Clustering1D


@runtime_checkable
class NBinsSelector(Protocol):
    """A rule that chooses the number of bins from a sweep of clusterings."""

    def select(self, values: npt.NDArray[np.float64], candidates: Sequence[CandidateFit]) -> int:
        """Choose the number of bins.

        Parameters
        ----------
        values: numpy.ndarray of float64, shape (n_samples,)
            The values of the feature.
        candidates: Sequence[CandidateFit]
            The clusterings for consecutive numbers of bins, in increasing order. The sequence is not empty.

        Returns
        -------
        int
            The ``n_bins`` of one of the candidates.

        """
        ...  # pragma: no cover -- a Protocol method has no body to run


ScoreFunction: TypeAlias = Callable[[npt.NDArray[np.float64], CandidateFit], float]


@attrs.frozen
class MaxScore:
    """Choose the candidate with the highest score. A tie goes to the smallest number of bins.

    Attributes
    ----------
    score: Callable
        A function of the values and one candidate that returns a number. Higher is better.

    Examples
    --------
    >>> from optimal_discretizer import MaxScore, OptimalDiscretizer
    >>> fewest_bins_with_low_inertia = MaxScore(lambda values, fit: -fit.clustering.inertia - fit.n_bins)
    >>> discretizer = OptimalDiscretizer(n_bins=None, scorer=fewest_bins_with_low_inertia)

    """

    score: ScoreFunction

    def select(self, values: npt.NDArray[np.float64], candidates: Sequence[CandidateFit]) -> int:
        """Return the ``n_bins`` of the first candidate with the highest score.

        Parameters
        ----------
        values: numpy.ndarray of float64, shape (n_samples,)
            The values of the feature.
        candidates: Sequence[CandidateFit]
            The clusterings to score.

        Returns
        -------
        int
            The chosen number of bins.

        """
        scores = [float(self.score(values, candidate)) for candidate in candidates]
        return candidates[int(np.argmax(scores))].n_bins


@attrs.frozen
class MDLCodeLength:
    """The two parts of the minimum description length of a clustering, in bits.

    Attributes
    ----------
    model_bits: float
        The code length of the centroids.
    data_bits: float
        The code length of the residuals, given the centroids.

    """

    model_bits: float
    data_bits: float


def resolve_min_std(values: npt.NDArray[np.float64], min_std: float | None) -> float:
    """Return the smallest residual standard deviation that the MDL code can encode.

    Parameters
    ----------
    values: numpy.ndarray of float64, shape (n_samples,)
        The values of the feature.
    min_std: float or None
        A floor that the caller sets. ``None`` uses half of the smallest gap between two distinct values, or the
        machine epsilon if the values hold fewer than two distinct numbers.

    Returns
    -------
    float
        A positive standard deviation.

    Raises
    ------
    ParameterRangeError
        If ``min_std`` is set and not positive.

    """
    if min_std is not None:
        if min_std <= 0:
            raise ParameterRangeError(name="min_std", value=min_std, allowed="greater than 0")
        return float(min_std)
    distinct_values = np.unique(values)
    if distinct_values.size < _MIN_DISTINCT_VALUES_FOR_GAP:
        return float(np.finfo(np.float64).eps)
    return float(0.5 * np.diff(distinct_values).min())


def mdl_code_length(
    values: npt.NDArray[np.float64],
    candidate: CandidateFit,
    min_std: float | None = None,
) -> MDLCodeLength:
    """Compute the two-part MDL code length of a clustering with a Gaussian code for the residuals of each bin.

    ``model_bits = n_bins * 0.5 * log2(n_samples) + log2(n_bins)``, and
    ``data_bits = sum over bins j of n_j * 0.5 * log2(2 * pi * e * var_j)``, where ``var_j`` is the biased variance of
    the residuals of bin ``j``, floored at ``min_std ** 2``. Among the distributions with a given variance, the
    Gaussian has the largest differential entropy, so this code does not understate the bits of the residuals.

    Parameters
    ----------
    values: numpy.ndarray of float64, shape (n_samples,)
        The values of the feature.
    candidate: CandidateFit
        The clustering to encode.
    min_std: float or None
        The floor of the residual standard deviation. See ``resolve_min_std``.

    Returns
    -------
    MDLCodeLength
        The bits of the model and the bits of the data.

    """
    clustering = candidate.clustering
    floor_variance = resolve_min_std(values, min_std) ** 2
    residuals = values - clustering.centroids[clustering.labels]
    counts = np.bincount(clustering.labels, minlength=candidate.n_bins)
    squared_residual_sums = np.bincount(clustering.labels, weights=np.square(residuals), minlength=candidate.n_bins)
    variances = np.maximum(squared_residual_sums / counts, floor_variance)
    entropy_bits = 0.5 * np.log2(2.0 * np.pi * np.e * variances)
    data_bits = float(np.sum(counts * entropy_bits))
    model_bits = float(candidate.n_bins * 0.5 * np.log2(values.size) + np.log2(candidate.n_bins))
    return MDLCodeLength(model_bits=model_bits, data_bits=data_bits)


def mdl_gaussian_score(values: npt.NDArray[np.float64], candidate: CandidateFit) -> float:
    """Return the negative total MDL code length of a clustering, so that a higher score is a shorter code.

    Parameters
    ----------
    values: numpy.ndarray of float64, shape (n_samples,)
        The values of the feature.
    candidate: CandidateFit
        The clustering to score.

    Returns
    -------
    float
        ``-(model_bits + data_bits)`` of ``mdl_code_length``, with the default floor.

    """
    code_length = mdl_code_length(values, candidate)
    return -(code_length.model_bits + code_length.data_bits)


@attrs.frozen
class SecondDifferenceSelector:
    """Choose the elbow of the inertia curve: the number of bins with the largest second difference.

    The second difference at ``n`` is ``inertia(n - 1) - 2 * inertia(n) + inertia(n + 1)``. It is large where the
    inertia stops falling fast. A tie goes to the smallest number of bins. With fewer than three candidates, no
    second difference exists, and the selector returns the first candidate with a warning.
    """

    def select(self, values: npt.NDArray[np.float64], candidates: Sequence[CandidateFit]) -> int:  # ruff: ignore[no-self-use] -- the method fulfils the NBinsSelector protocol, which the other selectors need with their state
        """Return the ``n_bins`` with the largest second difference of the inertia.

        Parameters
        ----------
        values: numpy.ndarray of float64, shape (n_samples,)
            Not read: the second difference depends on the inertia only.
        candidates: Sequence[CandidateFit]
            At least three clusterings for consecutive numbers of bins, or the selector warns.

        Returns
        -------
        int
            The middle number of bins of the three with the largest curvature.

        Warns
        -----
        UserWarning
            With fewer than three candidates.

        """
        del values
        if len(candidates) < _SECOND_DIFFERENCE_NEIGHBOURS:
            warnings.warn(
                "the second difference needs at least three candidates; using the smallest number of bins",
                UserWarning,
                stacklevel=2,
            )
            return candidates[0].n_bins
        inertia = np.array([candidate.clustering.inertia for candidate in candidates])
        second_differences = inertia[:-2] - 2.0 * inertia[1:-1] + inertia[2:]
        return candidates[int(np.argmax(second_differences)) + 1].n_bins


@attrs.frozen(kw_only=True)
class KneeSettings:
    """The settings of the Kneedle algorithm of Satopää, Albrecht, Irwin and Raghavan (ICDCSW 2011).

    Attributes
    ----------
    curve: {"convex", "concave"}
        The shape of the curve.
    direction: {"decreasing", "increasing"}
        The direction of the curve.
    sensitivity: float
        The sensitivity ``S``: a larger value finds fewer knees.

    """

    curve: KneeCurve = "convex"
    direction: KneeDirection = "decreasing"
    sensitivity: float = 1.0

    def knee_position(self, horizontal: npt.NDArray[np.float64], vertical: npt.NDArray[np.float64]) -> int | None:
        """Return the index of the point nearest to the knee that ``kneed.KneeLocator`` finds.

        Parameters
        ----------
        horizontal: numpy.ndarray of float64
            The horizontal coordinates of the curve, in increasing order.
        vertical: numpy.ndarray of float64
            The vertical coordinates of the curve.

        Returns
        -------
        int or None
            The index, or ``None`` if the algorithm finds no knee.

        """
        knee = KneeLocator(horizontal, vertical, S=self.sensitivity, curve=self.curve, direction=self.direction).knee
        if knee is None:
            return None
        return int(np.argmin(np.abs(horizontal - float(knee))))


@attrs.frozen(kw_only=True)
class MDLBitsKneeSelector:
    """Choose the knee of the curve of data bits against model bits.

    The curve has ``L(model)`` on the horizontal axis and ``L(data | model)`` on the vertical axis. Model bits rise as
    data bits fall, and the knee is where the two costs balance, as in the L-curve criterion of regularization. The
    Kneedle algorithm of Satopää, Albrecht, Irwin and Raghavan (ICDCSW 2011), through ``kneed.KneeLocator``, finds the
    knee. If it finds none, the selector returns the candidate with the shortest total code, with a warning.

    Attributes
    ----------
    min_std: float or None
        The floor of the residual standard deviation. See ``resolve_min_std``.
    knee: KneeSettings
        The settings of the Kneedle algorithm.

    """

    min_std: float | None = None
    knee: KneeSettings = KneeSettings()

    def select(self, values: npt.NDArray[np.float64], candidates: Sequence[CandidateFit]) -> int:
        """Return the ``n_bins`` at the knee of the MDL curve.

        Parameters
        ----------
        values: numpy.ndarray of float64, shape (n_samples,)
            The values of the feature.
        candidates: Sequence[CandidateFit]
            The clusterings for consecutive numbers of bins.

        Returns
        -------
        int
            The chosen number of bins.

        Warns
        -----
        UserWarning
            If the Kneedle algorithm finds no knee.

        """
        code_lengths = [mdl_code_length(values, candidate, self.min_std) for candidate in candidates]
        model_bits = np.array([code_length.model_bits for code_length in code_lengths])
        data_bits = np.array([code_length.data_bits for code_length in code_lengths])
        position = self.knee.knee_position(model_bits, data_bits)
        if position is None:
            warnings.warn(
                "KneeLocator found no knee of the MDL curve; using the shortest total code length",
                UserWarning,
                stacklevel=2,
            )
            position = int(np.argmin(model_bits + data_bits))
        return candidates[position].n_bins


@attrs.frozen(kw_only=True)
class KneedInertiaSelector:
    """Choose the knee of the curve of inertia against the number of bins.

    The Kneedle algorithm of Satopää, Albrecht, Irwin and Raghavan (ICDCSW 2011), through ``kneed.KneeLocator``, finds
    the knee. If it finds none, the selector returns the smallest number of bins, with a warning.

    Attributes
    ----------
    knee: KneeSettings
        The settings of the Kneedle algorithm.

    """

    knee: KneeSettings = KneeSettings()

    def select(self, values: npt.NDArray[np.float64], candidates: Sequence[CandidateFit]) -> int:
        """Return the ``n_bins`` at the knee of the inertia curve.

        Parameters
        ----------
        values: numpy.ndarray of float64, shape (n_samples,)
            Not read: the curve is the inertia against the number of bins.
        candidates: Sequence[CandidateFit]
            The sweep, as for every selector.

        Returns
        -------
        int
            The number of bins at the knee, or the smallest one if no knee exists.

        Warns
        -----
        UserWarning
            When ``KneeLocator`` finds no knee.

        """
        del values
        bin_counts = np.array([candidate.n_bins for candidate in candidates], dtype=np.float64)
        inertia = np.array([candidate.clustering.inertia for candidate in candidates])
        position = self.knee.knee_position(bin_counts, inertia)
        if position is None:
            warnings.warn(
                "KneeLocator found no knee of the inertia curve; using the smallest number of bins",
                UserWarning,
                stacklevel=2,
            )
            position = 0
        return candidates[position].n_bins


SCORERS: Mapping[str, NBinsSelector] = {
    "second_difference": SecondDifferenceSelector(),
    "mdl_gaussian": MaxScore(mdl_gaussian_score),
    "mdl_bits_knee": MDLBitsKneeSelector(),
    "kneed_inertia": KneedInertiaSelector(),
}
"""The selectors that ``OptimalDiscretizer(scorer=...)`` accepts by name."""


def resolve_scorer(scorer: str | NBinsSelector) -> NBinsSelector:
    """Return the selector for a name of ``SCORERS``, or the selector itself.

    Parameters
    ----------
    scorer: str or NBinsSelector
        A name of ``SCORERS`` or a selector.

    Returns
    -------
    NBinsSelector
        The selector.

    Raises
    ------
    ScorerError
        If the name is not in ``SCORERS``.

    """
    # The one place where a name enters: narrow the union once, then every caller works with a selector.
    if not isinstance(scorer, str):
        return scorer
    if scorer not in SCORERS:
        msg = f"unknown scorer {scorer!r}; the names are {sorted(SCORERS)}"
        raise ScorerError(msg)
    return SCORERS[scorer]
