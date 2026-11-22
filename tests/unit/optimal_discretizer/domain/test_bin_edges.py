"""Tests of the bin edges."""

import numpy as np

from optimal_discretizer.domain.bin_edges import centroids_to_edges


def test_edges_are_the_midpoints_with_infinite_ends() -> None:
    assert centroids_to_edges(np.array([0.0, 2.0, 10.0])).tolist() == [-np.inf, 1.0, 6.0, np.inf]


def test_one_centroid_gives_one_bin_over_every_value() -> None:
    assert centroids_to_edges(np.array([3.0])).tolist() == [-np.inf, np.inf]
