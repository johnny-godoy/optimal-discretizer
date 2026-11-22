"""Tests of the scikit-learn transformer."""

from collections.abc import Callable, Sequence

import numpy as np
import numpy.typing as npt
import pytest
from sklearn.base import BaseEstimator, clone
from sklearn.exceptions import NotFittedError
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.utils.estimator_checks import estimator_checks_generator  # pyrefly: ignore[missing-module-attribute] -- the scikit-learn stubs that pyrefly bundles predate estimator_checks_generator, which scikit-learn 1.6 added

from optimal_discretizer.adapters.discretizer import OptimalDiscretizer
from optimal_discretizer.core.exceptions import BinCountWarning, ParameterRangeError, ScorerError
from optimal_discretizer.domain.clustering import kmeans_1d
from optimal_discretizer.domain.scorers import CandidateFit, MaxScore


def random_data(sample_count: int = 200, feature_count: int = 3) -> npt.NDArray[np.float64]:
    return np.random.default_rng(0).normal(size=(sample_count, feature_count))


ESTIMATORS = [OptimalDiscretizer(), OptimalDiscretizer(n_bins=None, scorer="mdl_bits_knee")]
SKLEARN_CHECKS: list[tuple[BaseEstimator, Callable[[BaseEstimator], None]]] = [
    (estimator, check) for candidate in ESTIMATORS for estimator, check in estimator_checks_generator(candidate)
]


def check_id(case: tuple[BaseEstimator, Callable[[BaseEstimator], None]]) -> str:
    estimator, check = case
    return f"{estimator!r}-{getattr(check, 'func', check).__name__}"


@pytest.mark.parametrize("case", SKLEARN_CHECKS, ids=[check_id(case) for case in SKLEARN_CHECKS])
def test_the_estimator_passes_the_checks_of_scikit_learn(
    case: tuple[BaseEstimator, Callable[[BaseEstimator], None]],
) -> None:
    estimator, check = case
    check(estimator)


def test_fit_stores_the_exact_clustering_of_each_feature() -> None:
    data = random_data()
    discretizer = OptimalDiscretizer(n_bins=4).fit(data)
    for feature_index in range(data.shape[1]):
        clustering = kmeans_1d(data[:, feature_index], 4)
        np.testing.assert_array_equal(discretizer.centroids_[feature_index], clustering.centroids)
        assert discretizer.inertia_[feature_index] == pytest.approx(clustering.inertia)
    assert discretizer.n_bins_.tolist() == [4, 4, 4]
    assert discretizer.n_features_in_ == 3


def test_transform_assigns_each_training_value_to_its_cluster() -> None:
    data = random_data()
    discretizer = OptimalDiscretizer(n_bins=5).fit(data)
    bins = discretizer.transform(data)
    for feature_index in range(data.shape[1]):
        np.testing.assert_array_equal(bins[:, feature_index], kmeans_1d(data[:, feature_index], 5).labels)


def test_transform_gives_ordered_bins_from_zero() -> None:
    bins = OptimalDiscretizer(n_bins=3).fit_transform(np.array([[10.0], [20.0], [30.0], [40.0], [60.0]]))
    assert bins.ravel().tolist() == [0.0, 0.0, 1.0, 1.0, 2.0]
    assert bins.dtype == np.float64


def test_bin_edges_are_the_midpoints_of_the_centroids() -> None:
    discretizer = OptimalDiscretizer(n_bins=2).fit(np.array([[0.0], [1.0], [9.0], [10.0]]))
    assert discretizer.bin_edges_[0].tolist() == [-np.inf, 5.0, np.inf]


def test_the_estimator_works_in_a_pipeline() -> None:
    data = random_data()
    target = (data[:, 0] > 0).astype(int)
    pipeline = Pipeline([("bins", OptimalDiscretizer(n_bins=4)), ("model", LogisticRegression())])
    assert pipeline.fit(data, target).score(data, target) > 0.8


def test_clone_keeps_the_parameters() -> None:
    discretizer = OptimalDiscretizer(n_bins=None, n_bins_range=(2, 4), scorer="mdl_gaussian")
    assert clone(discretizer).get_params() == {"n_bins": None, "n_bins_range": (2, 4), "scorer": "mdl_gaussian"}


def test_transform_before_fit_fails() -> None:
    with pytest.raises(NotFittedError):
        OptimalDiscretizer().transform(random_data())


def test_transform_with_other_features_fails() -> None:
    discretizer = OptimalDiscretizer(n_bins=2).fit(random_data(feature_count=3))
    with pytest.raises(ValueError, match="features"):
        discretizer.transform(random_data(feature_count=2))


@pytest.mark.parametrize("bad_value", [np.nan, np.inf])
def test_fit_rejects_a_value_that_is_not_finite(bad_value: float) -> None:
    data = random_data()
    data[3, 1] = bad_value
    with pytest.raises(ValueError, match=r"NaN|infinity"):
        OptimalDiscretizer().fit(data)


def test_n_bins_below_one_is_rejected() -> None:
    with pytest.raises(ParameterRangeError, match="n_bins must be at least 1, got 0"):
        OptimalDiscretizer(n_bins=0).fit(random_data())


def test_a_feature_with_fewer_distinct_values_gets_one_bin_for_each_value() -> None:
    data = np.column_stack([np.repeat([1.0, 2.0], 10), np.arange(20.0)])
    with pytest.warns(BinCountWarning, match=r"features \[0\]"):
        discretizer = OptimalDiscretizer(n_bins=5).fit(data)
    assert discretizer.n_bins_.tolist() == [2, 5]
    assert discretizer.centroids_[0].tolist() == [1.0, 2.0]


def test_a_single_sample_gets_one_bin() -> None:
    with pytest.warns(BinCountWarning):
        discretizer = OptimalDiscretizer(n_bins=3).fit(np.array([[7.0, -1.0]]))
    assert discretizer.n_bins_.tolist() == [1, 1]
    assert discretizer.transform(np.array([[100.0, -100.0]])).tolist() == [[0.0, 0.0]]


def test_the_scorer_chooses_the_number_of_bins() -> None:
    random_generator = np.random.default_rng(0)
    centers = np.repeat(np.array([-5.0, 0.0, 5.0]), 80)
    data = np.round(centers + random_generator.normal(0.0, 0.3, size=centers.size)).reshape(-1, 1)
    discretizer = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 6), scorer="mdl_gaussian").fit(data)
    assert discretizer.n_bins_.tolist() == [3]


def test_the_scorer_sees_every_count_of_the_range() -> None:
    seen: list[int] = []

    def score(values: npt.NDArray[np.float64], fit: CandidateFit) -> float:
        del values
        seen.append(fit.n_bins)
        return float(fit.n_bins == 3)

    data = np.array([[1.0], [2.0], [10.0], [11.0], [12.0]])
    discretizer = OptimalDiscretizer(n_bins=None, n_bins_range=(2, 4), scorer=MaxScore(score)).fit(data)
    assert seen == [2, 3, 4]
    assert discretizer.n_bins_.tolist() == [3]


def test_the_default_range_goes_from_one_to_the_number_of_distinct_values() -> None:
    seen: list[int] = []

    def score(values: npt.NDArray[np.float64], fit: CandidateFit) -> float:
        del values
        seen.append(fit.n_bins)
        return 0.0

    OptimalDiscretizer(n_bins=None, scorer=MaxScore(score)).fit(np.array([[1.0], [2.0], [2.0], [11.0]]))
    assert seen == [1, 2, 3]


def test_a_range_above_the_distinct_values_is_cut_with_a_warning() -> None:
    data = np.repeat([0.0, 5.0], 5).reshape(-1, 1)
    with pytest.warns(BinCountWarning):
        discretizer = OptimalDiscretizer(n_bins=None, n_bins_range=(3, 6), scorer="mdl_gaussian").fit(data)
    assert discretizer.n_bins_.tolist() == [2]


def test_n_bins_none_needs_a_scorer() -> None:
    with pytest.raises(ScorerError, match="scorer must be set when n_bins is None"):
        OptimalDiscretizer(n_bins=None).fit(random_data())


@pytest.mark.parametrize(
    ("bins_range", "message"),
    [
        ((0, 3), r"n_bins_range\[0\] must be at least 1, got 0"),
        ((3, 2), r"n_bins_range\[1\] must be at least 3, got 2"),
    ],
)
def test_an_invalid_range_is_rejected(bins_range: tuple[int, int], message: str) -> None:
    with pytest.raises(ParameterRangeError, match=message):
        OptimalDiscretizer(n_bins=None, n_bins_range=bins_range, scorer="mdl_gaussian").fit(random_data())


class OutOfRangeSelector:
    """A selector that breaks its contract: it returns a number of bins that it was not given."""

    def select(self, values: npt.NDArray[np.float64], candidates: Sequence[CandidateFit]) -> int:  # ruff: ignore[no-self-use] -- the method fulfils the NBinsSelector protocol
        """Return one more than the largest candidate.

        Returns
        -------
        int
            A number of bins that the discretizer did not offer.

        """
        del values
        return candidates[-1].n_bins + 1


def test_a_scorer_that_chooses_a_count_it_was_not_given_is_rejected() -> None:
    discretizer = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 3), scorer=OutOfRangeSelector())
    with pytest.raises(ScorerError, match="chose n_bins=4, which is not between 1 and 3"):
        discretizer.fit(random_data())


def test_feature_names_pass_through() -> None:
    discretizer = OptimalDiscretizer(n_bins=2).fit(random_data(feature_count=2))
    assert discretizer.get_feature_names_out().tolist() == ["x0", "x1"]
