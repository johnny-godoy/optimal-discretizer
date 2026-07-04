"""Tests for scorer implementations."""

from typing import ClassVar

import numpy as np
import pytest

from src._core import cluster  # noqa: PLC2701
from src.scorers import (
    CandidateFit,
    KneedInertiaScorer,
    MDLBitsKneeScorer,
    ScorerProtocol,
    mdl_gaussian_scorer,
    second_difference_scorer,
)
from src.transformer import OptimalDiscretizer


def make_quantized_three_cluster_data() -> np.ndarray:
    rng = np.random.default_rng(0)
    x = np.concatenate(
        [
            rng.normal(-5.0, 0.3, size=80),
            rng.normal(0.0, 0.3, size=80),
            rng.normal(5.0, 0.3, size=80),
        ],
    )
    return np.round(x, decimals=0).astype(np.float64)


def make_integer_cluster_data() -> np.ndarray:
    return np.repeat(np.array([-10.0, 0.0, 10.0], dtype=np.float64), repeats=30)


def fit_candidate(x: np.ndarray, n_bins: int) -> CandidateFit:
    labels, centroids = cluster(np.ascontiguousarray(x), n_bins)
    residuals = x - centroids[labels]
    inertia = float(np.square(residuals).sum())
    return CandidateFit(n_bins=n_bins, labels=labels, centroids=centroids, inertia=inertia)


def build_candidates(x: np.ndarray, n_bins_min: int, n_bins_max: int) -> list[CandidateFit]:
    return [fit_candidate(x, n_bins) for n_bins in range(n_bins_min, n_bins_max + 1)]


class TestMDLGaussianScorer:
    def test_penalizes_too_few_bins(self):
        x = make_integer_cluster_data()
        score_one = mdl_gaussian_scorer(x, **fit_candidate(x, 1)._asdict())
        score_three = mdl_gaussian_scorer(x, **fit_candidate(x, 3)._asdict())
        assert score_three > score_one

    def test_penalizes_too_many_bins(self):
        x = make_integer_cluster_data()
        score_three = mdl_gaussian_scorer(x, **fit_candidate(x, 3)._asdict())
        score_six = mdl_gaussian_scorer(x, **fit_candidate(x, 6)._asdict())
        assert score_three > score_six

    def test_prefers_reasonable_middle_on_quantized_multicluster_data(self):
        x = make_quantized_three_cluster_data()
        scores = {
            n_bins: mdl_gaussian_scorer(x, **fit_candidate(x, n_bins)._asdict())
            for n_bins in range(1, 7)
        }
        assert max(scores, key=scores.get) == 3


class TestCurveScorers:
    @pytest.mark.parametrize("scorer_name", ["mdl_bits_knee", "kneed_inertia"])
    def test_curve_scorers_select_reasonable_middle(self, scorer_name: str):
        x = make_quantized_three_cluster_data()
        disc = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 6), scorer=scorer_name)
        disc.fit(x.reshape(-1, 1))
        assert disc.n_bins_[0] == 3

    def test_mdl_bits_knee_falls_back_to_minimum_total_bits(self):
        x = make_quantized_three_cluster_data()
        candidates = build_candidates(x, 1, 2)
        scorer = MDLBitsKneeScorer()
        with pytest.warns(UserWarning, match="minimum total MDL code length"):
            chosen_n_bins = scorer(x, candidates)
        total_bits = {
            candidate.n_bins: -mdl_gaussian_scorer(x, **candidate._asdict())
            for candidate in candidates
        }
        assert chosen_n_bins == min(total_bits, key=total_bits.get)

    def test_kneed_inertia_falls_back_to_smallest_candidate(self):
        x = np.array([0.0, 1.0, 2.0], dtype=np.float64)
        labels = np.array([0, 0, 0], dtype=np.int64)
        centroids = np.array([1.0], dtype=np.float64)
        candidates = [
            CandidateFit(n_bins=1, labels=labels, centroids=centroids, inertia=2.0),
            CandidateFit(n_bins=2, labels=labels, centroids=centroids, inertia=1.0),
        ]
        scorer = KneedInertiaScorer()
        with pytest.warns(UserWarning, match="smallest evaluated n_bins"):
            chosen_n_bins = scorer(x, candidates)
        assert chosen_n_bins == 1

    def test_curve_scorer_invalid_choice_raises(self):
        class InvalidCurveScorer:
            is_curve_scorer: ClassVar[bool] = True

            def __call__(self, x: np.ndarray, candidates: list[CandidateFit]) -> int:  # noqa: ARG002
                return candidates[-1].n_bins + 1

        x = make_integer_cluster_data().reshape(-1, 1)
        disc = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 3), scorer=InvalidCurveScorer())
        with pytest.raises(ValueError, match="not among the candidates evaluated"):
            disc.fit(x)


class TestPointScorerRegression:
    @pytest.mark.parametrize("scorer", [second_difference_scorer, mdl_gaussian_scorer])
    def test_point_scorers_match_direct_argmax(self, scorer: ScorerProtocol):
        x = make_quantized_three_cluster_data()
        scores = {
            candidate.n_bins: scorer(
                x=x,
                labels=candidate.labels,
                centroids=candidate.centroids,
                n_bins=candidate.n_bins,
                inertia=candidate.inertia,
            )
            for candidate in build_candidates(x, 1, 5)
        }
        expected_n_bins = max(scores, key=scores.get)

        disc = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 5), scorer=scorer)
        disc.fit(x.reshape(-1, 1))
        assert disc.n_bins_[0] == expected_n_bins
