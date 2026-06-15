"""Tests for OptimalDiscretizer."""

import numpy as np
import pytest
from optimal_discretizer._core import cluster  # noqa: PLC2701


class TestClusterCore:
    """Tests for the low-level _core.cluster function."""

    def test_simple_two_clusters(self):
        data = np.array([1.0, 2.0, 10.0, 11.0], dtype=np.float64)
        labels, centroids = cluster(data, 2)
        assert labels.shape == (4,)
        assert centroids.shape == (2,)
        # The two natural groups should be clearly separated
        assert labels[0] == labels[1]
        assert labels[2] == labels[3]
        assert labels[0] != labels[2]

    def test_k_equals_n(self):
        data = np.array([3.0, 1.0, 4.0, 2.0, 5.0], dtype=np.float64)
        labels, _ = cluster(data, 5)
        # Each element is its own cluster
        assert len(set(labels.tolist())) == 5

    def test_k_equals_1(self):
        data = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
        labels, centroids = cluster(data, 1)
        assert (labels == 0).all()
        assert centroids[0] == pytest.approx(2.5)

    def test_labels_are_ordinal(self):
        """Cluster 0 should contain the smallest values."""
        data = np.array([10.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float64)
        _, centroids = cluster(data, 3)
        # Centroids must be in ascending order
        assert list(centroids) == sorted(centroids)

    def test_invalid_k_zero(self):
        with pytest.raises((ValueError, Exception)):
            cluster(np.array([1.0, 2.0], dtype=np.float64), 0)

    def test_invalid_k_too_large(self):
        with pytest.raises((ValueError, Exception)):
            cluster(np.array([1.0, 2.0], dtype=np.float64), 5)
