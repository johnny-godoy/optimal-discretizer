"""Utilities for the optimal discretizer."""

import numpy as np


def centroids_to_edges(centroids: np.ndarray) -> np.ndarray:
    """Convert sorted centroid array to bin-edge thresholds.

    Edges are midpoints between consecutive centroids, with ``-inf`` and
    ``+inf`` as the outermost sentinels.

    Parameters
    ----------
    centroids : ndarray of shape (n_bins,)
        Sorted array of centroids.

    Returns
    -------
    edges : ndarray of shape (n_bins + 1,)
        Bin-edge thresholds derived from centroids.  Each threshold is the
        midpoint between consecutive centroids, with ``-inf`` and ``+inf`` as
        the outermost sentinels.
    """
    mid = (centroids[:-1] + centroids[1:]) / 2.0
    return np.concatenate([[-np.inf], mid, [np.inf]])
