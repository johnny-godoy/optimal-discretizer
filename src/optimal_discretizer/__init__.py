"""Exact 1-D k-means discretization for scikit-learn, with a Cython core."""

from importlib.metadata import version

from beartype import BeartypeConf
from beartype.claw import beartype_this_package

# The hook must run before any submodule import, or those modules stay unchecked.
# The numeric tower lets an int satisfy a float hint, as PEP 484 says.
# Checking annotated variables is off, because structlog's lazy logger proxy does not match its own logger type.
beartype_this_package(conf=BeartypeConf(is_pep484_tower=True, claw_is_pep526=False))  # ruff: ignore[non-empty-init-module] -- the hook must run before the submodule imports below

from optimal_discretizer.adapters import OptimalDiscretizer  # ruff: ignore[module-import-not-at-top-of-file] -- the beartype hook must run first
from optimal_discretizer.core import (  # ruff: ignore[module-import-not-at-top-of-file] -- the beartype hook must run first
    BinCountWarning,
    EmptyInputError,
    InputShapeError,
    NonFiniteValueError,
    OptimalDiscretizerError,
    ParameterRangeError,
    ScorerError,
)
from optimal_discretizer.domain import (  # ruff: ignore[module-import-not-at-top-of-file] -- the beartype hook must run first
    SCORERS,
    CandidateFit,
    Clustering1D,
    KneedInertiaSelector,
    KneeSettings,
    MaxScore,
    MDLBitsKneeSelector,
    MDLCodeLength,
    NBinsSelector,
    SecondDifferenceSelector,
    centroids_to_edges,
    kmeans_1d,
    mdl_code_length,
    mdl_gaussian_score,
)

__version__: str = version("optimal-discretizer")

__all__ = [
    "SCORERS",
    "BinCountWarning",
    "CandidateFit",
    "Clustering1D",
    "EmptyInputError",
    "InputShapeError",
    "KneeSettings",
    "KneedInertiaSelector",
    "MDLBitsKneeSelector",
    "MDLCodeLength",
    "MaxScore",
    "NBinsSelector",
    "NonFiniteValueError",
    "OptimalDiscretizer",
    "OptimalDiscretizerError",
    "ParameterRangeError",
    "ScorerError",
    "SecondDifferenceSelector",
    "__version__",
    "centroids_to_edges",
    "kmeans_1d",
    "mdl_code_length",
    "mdl_gaussian_score",
]
