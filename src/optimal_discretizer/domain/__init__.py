"""Pure logic: exact 1-D k-means, the bin edges and the scorers that choose the number of bins. No I/O."""

from optimal_discretizer.domain.bin_edges import centroids_to_edges
from optimal_discretizer.domain.clustering import Clustering1D, kmeans_1d
from optimal_discretizer.domain.scorers import (
    SCORERS,
    CandidateFit,
    KneedInertiaSelector,
    KneeSettings,
    MaxScore,
    MDLBitsKneeSelector,
    MDLCodeLength,
    NBinsSelector,
    SecondDifferenceSelector,
    mdl_code_length,
    mdl_gaussian_score,
)

__all__ = [
    "SCORERS",
    "CandidateFit",
    "Clustering1D",
    "KneeSettings",
    "KneedInertiaSelector",
    "MDLBitsKneeSelector",
    "MDLCodeLength",
    "MaxScore",
    "NBinsSelector",
    "SecondDifferenceSelector",
    "centroids_to_edges",
    "kmeans_1d",
    "mdl_code_length",
    "mdl_gaussian_score",
]
