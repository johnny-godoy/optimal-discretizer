"""Tests for OptimalDiscretizer."""

import numpy as np
import pytest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.estimator_checks import parametrize_with_checks

from optimal_discretizer import OptimalDiscretizer


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------


class TestClusterCore:
    """Tests for the low-level _core.cluster function."""

    def test_simple_two_clusters(self):
        from optimal_discretizer._core import cluster

        data = np.array([1.0, 2.0, 10.0, 11.0], dtype=np.float64)
        labels, centroids = cluster(data, 2)
        assert labels.shape == (4,)
        assert centroids.shape == (2,)
        # The two natural groups should be clearly separated
        assert labels[0] == labels[1]
        assert labels[2] == labels[3]
        assert labels[0] != labels[2]

    def test_k_equals_n(self):
        from optimal_discretizer._core import cluster

        data = np.array([3.0, 1.0, 4.0, 2.0, 5.0], dtype=np.float64)
        labels, centroids = cluster(data, 5)
        # Each element is its own cluster
        assert len(set(labels.tolist())) == 5

    def test_k_equals_1(self):
        from optimal_discretizer._core import cluster

        data = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
        labels, centroids = cluster(data, 1)
        assert (labels == 0).all()
        assert centroids[0] == pytest.approx(2.5)

    def test_labels_are_ordinal(self):
        """Cluster 0 should contain the smallest values."""
        from optimal_discretizer._core import cluster

        data = np.array([10.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float64)
        labels, centroids = cluster(data, 3)
        # Centroids must be in ascending order
        assert list(centroids) == sorted(centroids)

    def test_invalid_k_zero(self):
        from optimal_discretizer._core import cluster

        with pytest.raises((ValueError, Exception)):
            cluster(np.array([1.0, 2.0], dtype=np.float64), 0)

    def test_invalid_k_too_large(self):
        from optimal_discretizer._core import cluster

        with pytest.raises((ValueError, Exception)):
            cluster(np.array([1.0, 2.0], dtype=np.float64), 5)


# ---------------------------------------------------------------------------
# OptimalDiscretizer transformer
# ---------------------------------------------------------------------------


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
        pipe = Pipeline(
            [("scaler", StandardScaler()), ("disc", OptimalDiscretizer(n_bins=3))]
        )
        X_out = pipe.fit_transform(X)
        assert X_out.shape == (60, 2)

    def test_get_set_params(self):
        disc = OptimalDiscretizer(n_bins=7)
        assert disc.get_params()["n_bins"] == 7
        disc.set_params(n_bins=3)
        assert disc.n_bins == 3

    def test_invalid_n_bins_zero(self):
        X = np.array([[1.0], [2.0], [3.0]])
        with pytest.raises(ValueError):
            OptimalDiscretizer(n_bins=0).fit(X)

    def test_invalid_n_bins_too_large(self):
        X = np.array([[1.0], [2.0]])
        with pytest.raises(ValueError):
            OptimalDiscretizer(n_bins=5).fit(X)

    def test_transform_feature_mismatch(self):
        X_train = np.random.default_rng(0).normal(size=(20, 3))
        X_test = np.random.default_rng(1).normal(size=(10, 2))
        disc = OptimalDiscretizer(n_bins=3).fit(X_train)
        with pytest.raises(ValueError):
            disc.transform(X_test)

    def test_not_fitted_raises(self):
        from sklearn.exceptions import NotFittedError

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


# ---------------------------------------------------------------------------
# Scikit-learn estimator compatibility check
# ---------------------------------------------------------------------------


@parametrize_with_checks([OptimalDiscretizer()])
def test_sklearn_compatible(estimator, check):
    check(estimator)
