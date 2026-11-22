"""Exact 1-D k-means discretization for scikit-learn, with a Cython core."""

from importlib.metadata import version

from beartype import BeartypeConf
from beartype.claw import beartype_this_package

# The hook must run before any submodule import, or those modules stay unchecked.
# The numeric tower lets an int satisfy a float hint, as PEP 484 says.
# Checking annotated variables is off, because structlog's lazy logger proxy does not match its own logger type.
beartype_this_package(conf=BeartypeConf(is_pep484_tower=True, claw_is_pep526=False))  # ruff: ignore[non-empty-init-module] -- the hook must run before the submodule imports below

from optimal_discretizer.core.exceptions import EmptyInputError, OptimalDiscretizerError  # ruff: ignore[module-import-not-at-top-of-file] -- the beartype hook must run first

__version__: str = version("optimal-discretizer")

__all__ = [
    "EmptyInputError",
    "OptimalDiscretizerError",
    "__version__",
]
