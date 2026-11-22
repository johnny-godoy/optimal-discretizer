"""Tests of the scorers that choose the number of bins."""

import numpy as np
import numpy.typing as npt
import pytest

from optimal_discretizer.core.exceptions import ParameterRangeError, ScorerError
from optimal_discretizer.domain.clustering import Clustering1D, kmeans_1d
from optimal_discretizer.domain.scorers import (
    SCORERS,
    CandidateFit,
    KneedInertiaSelector,
    KneeSettings,
    MaxScore,
    MDLBitsKneeSelector,
    SecondDifferenceSelector,
    mdl_code_length,
    mdl_gaussian_score,
    resolve_min_std,
    resolve_scorer,
)


def three_rounded_clusters() -> npt.NDArray[np.float64]:
    random_generator = np.random.default_rng(0)
    values = np.concatenate([random_generator.normal(center, 0.3, size=80) for center in (-5.0, 0.0, 5.0)])
    return np.round(values)


def three_integer_clusters() -> npt.NDArray[np.float64]:
    return np.repeat(np.array([-10.0, 0.0, 10.0]), repeats=30)


def candidates_for(values: npt.NDArray[np.float64], smallest: int, largest: int) -> list[CandidateFit]:
    return [CandidateFit(n_bins=count, clustering=kmeans_1d(values, count)) for count in range(smallest, largest + 1)]


def candidates_with_inertia(inertia: list[float]) -> list[CandidateFit]:
    clustering = Clustering1D(labels=np.zeros(2, dtype=np.int64), centroids=np.zeros(1), inertia=0.0)
    return [
        CandidateFit(n_bins=position + 1, clustering=Clustering1D(clustering.labels, clustering.centroids, value))
        for position, value in enumerate(inertia)
    ]


def test_mdl_gaussian_score_prefers_the_true_number_of_clusters() -> None:
    values = three_rounded_clusters()
    scores = {fit.n_bins: mdl_gaussian_score(values, fit) for fit in candidates_for(values, 1, 6)}
    assert max(scores, key=scores.__getitem__) == 3


def test_mdl_gaussian_score_penalizes_too_few_and_too_many_bins() -> None:
    values = three_integer_clusters()
    one, three, six = (
        mdl_gaussian_score(values, fit) for fit in candidates_for(values, 1, 6) if fit.n_bins in {1, 3, 6}
    )
    assert three > one
    assert three > six


def test_mdl_code_length_follows_its_formula() -> None:
    values = np.array([0.0, 2.0, 10.0, 14.0])
    fit = CandidateFit(n_bins=2, clustering=kmeans_1d(values, 2))
    code_length = mdl_code_length(values, fit, min_std=0.5)
    assert code_length.model_bits == pytest.approx(2 * 0.5 * np.log2(4) + np.log2(2))
    expected_data_bits = 2 * 0.5 * np.log2(2 * np.pi * np.e * 1.0) + 2 * 0.5 * np.log2(2 * np.pi * np.e * 4.0)
    assert code_length.data_bits == pytest.approx(expected_data_bits)


def test_mdl_code_length_floors_the_variance() -> None:
    values = np.array([1.0, 1.0, 5.0, 5.0])
    fit = CandidateFit(n_bins=2, clustering=kmeans_1d(values, 2))
    code_length = mdl_code_length(values, fit, min_std=2.0)
    assert code_length.data_bits == pytest.approx(4 * 0.5 * np.log2(2 * np.pi * np.e * 4.0))


def test_resolve_min_std_uses_half_of_the_smallest_gap() -> None:
    assert resolve_min_std(np.array([0.0, 3.0, 4.0, 4.0]), None) == pytest.approx(0.5)


def test_resolve_min_std_of_constant_values_is_the_machine_epsilon() -> None:
    assert resolve_min_std(np.array([2.0, 2.0]), None) == np.finfo(np.float64).eps


def test_resolve_min_std_keeps_a_positive_floor() -> None:
    assert resolve_min_std(np.array([0.0, 1.0]), 0.25) == pytest.approx(0.25)


@pytest.mark.parametrize("min_std", [0.0, -1.0])
def test_resolve_min_std_rejects_a_floor_that_is_not_positive(min_std: float) -> None:
    with pytest.raises(ParameterRangeError, match="min_std must be greater than 0"):
        resolve_min_std(np.array([0.0, 1.0]), min_std)


def test_max_score_returns_the_first_best_candidate() -> None:
    candidates = candidates_with_inertia([5.0, 1.0, 1.0])
    assert MaxScore(lambda _, fit: -fit.clustering.inertia).select(np.zeros(2), candidates) == 2


def test_second_difference_picks_the_largest_curvature() -> None:
    # Second differences: at 2: 100 - 40 + 30 = 90; at 3: 40 - 60 + 28 = 8; at 4: 30 - 56 + 27 = 1.
    candidates = candidates_with_inertia([100.0, 20.0, 30.0, 28.0, 27.0])
    assert SecondDifferenceSelector().select(np.zeros(2), candidates) == 2


def test_second_difference_breaks_a_tie_toward_fewer_bins() -> None:
    candidates = candidates_with_inertia([10.0, 5.0, 5.0, 0.0, 0.0])
    assert SecondDifferenceSelector().select(np.zeros(2), candidates) == 2


def test_second_difference_with_fewer_than_three_candidates_warns_and_takes_the_first() -> None:
    with pytest.warns(UserWarning, match="at least three candidates"):
        assert SecondDifferenceSelector().select(np.zeros(2), candidates_with_inertia([4.0, 1.0])) == 1


@pytest.mark.parametrize("selector", [MDLBitsKneeSelector(), KneedInertiaSelector()])
def test_knee_selectors_find_three_clusters(selector: MDLBitsKneeSelector | KneedInertiaSelector) -> None:
    values = three_rounded_clusters()
    assert selector.select(values, candidates_for(values, 1, 6)) == 3


def test_mdl_bits_knee_without_a_knee_warns_and_takes_the_shortest_code() -> None:
    values = three_rounded_clusters()
    candidates = candidates_for(values, 1, 2)
    with pytest.warns(UserWarning, match="shortest total code length"):
        chosen = MDLBitsKneeSelector().select(values, candidates)
    total_bits = {fit.n_bins: -mdl_gaussian_score(values, fit) for fit in candidates}
    assert chosen == min(total_bits, key=total_bits.__getitem__)


def test_mdl_bits_knee_passes_its_floor_to_the_code_length() -> None:
    values = three_integer_clusters()
    assert (
        MDLBitsKneeSelector(min_std=1.0, knee=KneeSettings(sensitivity=1.0)).select(
            values,
            candidates_for(values, 1, 6),
        )
        == 3
    )


def test_kneed_inertia_without_a_knee_warns_and_takes_the_smallest_count() -> None:
    with pytest.warns(UserWarning, match="smallest number of bins"):
        assert KneedInertiaSelector().select(np.zeros(2), candidates_with_inertia([2.0, 1.0])) == 1


def test_kneed_inertia_reads_its_curve_settings() -> None:
    rising = candidates_with_inertia([0.0, 60.0, 80.0, 90.0, 95.0, 97.0])
    assert (
        KneedInertiaSelector(knee=KneeSettings(curve="concave", direction="increasing")).select(np.zeros(2), rising)
        == 3
    )


def test_kneed_inertia_reads_its_sensitivity() -> None:
    rising = candidates_with_inertia([0.0, 60.0, 80.0, 90.0, 95.0, 97.0])
    with pytest.warns(UserWarning, match="no knee"):
        chosen = KneedInertiaSelector(
            knee=KneeSettings(curve="concave", direction="increasing", sensitivity=10.0),
        ).select(
            np.zeros(2),
            rising,
        )
    assert chosen == 1


def test_every_registered_scorer_is_a_selector() -> None:
    assert sorted(SCORERS) == ["kneed_inertia", "mdl_bits_knee", "mdl_gaussian", "second_difference"]


def test_resolve_scorer_looks_up_a_name() -> None:
    assert resolve_scorer("kneed_inertia") is SCORERS["kneed_inertia"]


def test_resolve_scorer_keeps_a_selector() -> None:
    selector = SecondDifferenceSelector()
    assert resolve_scorer(selector) is selector


def test_resolve_scorer_rejects_an_unknown_name() -> None:
    with pytest.raises(ScorerError, match="unknown scorer 'elbow'; the names are"):
        resolve_scorer("elbow")
