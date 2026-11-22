"""Turn the centroids of a clustering into the edges of the bins."""

import numpy as np
import numpy.typing as npt


def centroids_to_edges(centroids: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Return the bin edges: the midpoints between consecutive centroids, with ``-inf`` and ``+inf`` at the ends.

    A value between two edges is nearer to the centroid of that bin than to any other centroid, so the bins assign
    each value to its nearest centroid.

    Parameters
    ----------
    centroids: numpy.ndarray of float64, shape (n_bins,)
        The centroids in increasing order.

    Returns
    -------
    numpy.ndarray of float64, shape (n_bins + 1,)
        The edges in increasing order.

    Examples
    --------
    >>> import numpy as np
    >>> from optimal_discretizer import centroids_to_edges
    >>> centroids_to_edges(np.array([0.0, 2.0, 10.0])).tolist()
    [-inf, 1.0, 6.0, inf]

    """
    midpoints = (centroids[:-1] + centroids[1:]) / 2.0
    return np.concatenate(([-np.inf], midpoints, [np.inf]))
