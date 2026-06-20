"""Tests for OptimalDiscretizer."""

from collections.abc import Callable

import numpy as np
import pytest
from optimal_discretizer import OptimalDiscretizer
from sklearn.exceptions import NotFittedError
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.estimator_checks import parametrize_with_checks


class TestOptimalDiscretizer:
    def test_fit_transform_shape(self):
        rng = np.random.default_rng(42)
        X = rng.normal(size=(50, 3))
        disc = OptimalDiscretizer(n_bins=4)
        X_disc = disc.fit_transform(X)
        assert X_disc.shape == (50, 3)
        assert X_disc.dtype == np.float64

    def test_labels_in_range(self):
        rng = np.random.default_rng(0)
        X = rng.standard_normal((100, 2))
        disc = OptimalDiscretizer(n_bins=5)
        X_disc = disc.fit_transform(X)
        assert (X_disc >= 0).all()
        assert (X_disc < 5).all()

    def test_1d_input(self):
        x = np.array([[1.0], [2.0], [10.0], [11.0]])
        disc = OptimalDiscretizer(n_bins=2)
        X_disc = disc.fit_transform(x)
        assert X_disc.shape == (4, 1)

    def test_centroids_stored(self):
        X = np.array([[1.0, 2.0, 10.0, 11.0]]).T
        disc = OptimalDiscretizer(n_bins=2)
        disc.fit(X)
        assert len(disc.centroids_) == 1
        assert len(disc.centroids_[0]) == 2

    def test_bin_edges_stored(self):
        X = np.array([[1.0, 2.0, 10.0, 11.0]]).T
        disc = OptimalDiscretizer(n_bins=2)
        disc.fit(X)
        # Edges = n_bins + 1 (includes -inf and +inf sentinels)
        assert len(disc.bin_edges_[0]) == 3

    def test_transform_consistent_with_fit_transform(self):
        rng = np.random.default_rng(7)
        X = rng.normal(size=(80, 2))
        disc = OptimalDiscretizer(n_bins=4)
        disc.fit(X)
        assert np.array_equal(disc.transform(X), disc.fit_transform(X))

    def test_pipeline_compatible(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(60, 2))
        pipe = Pipeline([("scaler", StandardScaler()), ("disc", OptimalDiscretizer(n_bins=3))])
        X_out = pipe.fit_transform(X)
        assert X_out.shape == (60, 2)

    def test_get_set_params(self):
        disc = OptimalDiscretizer(n_bins=7)
        assert disc.get_params()["n_bins"] == 7
        disc.set_params(n_bins=3)
        assert disc.n_bins == 3

    def test_invalid_n_bins_zero(self):
        X = np.array([[1.0], [2.0], [3.0]])
        with pytest.raises(ValueError, match="n_bins must be >= 1"):
            OptimalDiscretizer(n_bins=0).fit(X)

    def test_invalid_n_bins_too_large(self):
        X = np.array([[1.0], [2.0]])
        with pytest.raises(ValueError, match="n_bins must be <= n_samples"):
            OptimalDiscretizer(n_bins=5).fit(X)

    def test_transform_feature_mismatch(self):
        X_train = np.random.default_rng(0).normal(size=(20, 3))
        X_test = np.random.default_rng(1).normal(size=(10, 2))
        disc = OptimalDiscretizer(n_bins=3).fit(X_train)
        with pytest.raises(ValueError, match="Number of features in X does not match the fitted data"):
            disc.transform(X_test)

    def test_not_fitted_raises(self):
        disc = OptimalDiscretizer(n_bins=3)
        with pytest.raises(NotFittedError):
            disc.transform(np.array([[1.0, 2.0]]))

    def test_n_bins_1(self):
        X = np.random.default_rng(5).normal(size=(30, 2))
        disc = OptimalDiscretizer(n_bins=1)
        X_disc = disc.fit_transform(X)
        assert (X_disc == 0).all()

    def test_ordered_clusters(self):
        """Higher bin index => higher centroid value."""
        rng = np.random.default_rng(3)
        X = rng.normal(size=(200, 1))
        disc = OptimalDiscretizer(n_bins=5)
        disc.fit(X)
        c = disc.centroids_[0]
        assert (np.diff(c) > 0).all()

    def test_search_n_bins_uses_scorer(self):
        X = np.array([[1.0], [2.0], [10.0], [11.0], [12.0]])

        def scorer(**kwargs):
            return float(kwargs["n_bins"])

        disc = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 3), scorer=scorer)
        disc.fit(X)
        assert disc.n_bins_[0] == 3

    def test_search_n_bins_default_range(self):
        X = np.array([[1.0], [2.0], [10.0], [11.0]])

        def scorer(**kwargs):
            return float(kwargs["n_bins"])

        disc = OptimalDiscretizer(n_bins=None, scorer=scorer)
        disc.fit(X)
        assert disc.n_bins_[0] == 4

    def test_both_n_bins_and_scorer_none_warns(self):
        X = np.array([[1.0], [2.0], [10.0], [11.0]])
        with pytest.warns(UserWarning, match="Both n_bins and scorer are None"):
            disc = OptimalDiscretizer(n_bins=None, scorer=None)
            disc.fit(X)
        assert disc.n_bins_[0] == 1

    def test_invalid_n_bins_range(self):
        X = np.array([[1.0], [2.0], [3.0]])
        with pytest.raises(ValueError, match="n_bins_min must be <= n_bins_max"):
            OptimalDiscretizer(n_bins=None, n_bins_range=(3, 1), scorer=lambda **_: 0.0).fit(X)


# ---------------------------------------------------------------------------
# Scikit-learn estimator compatibility check
# ---------------------------------------------------------------------------


@parametrize_with_checks([OptimalDiscretizer()])
def test_sklearn_compatible(estimator: OptimalDiscretizer, check: Callable) -> None:
    check(estimator)
