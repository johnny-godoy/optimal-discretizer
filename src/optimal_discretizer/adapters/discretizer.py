"""The scikit-learn transformer that discretizes each feature with exact 1-D k-means.

``OptimalDiscretizer`` connects the domain functions to the estimator API of scikit-learn: ``fit`` clusters each
column with ``kmeans_1d`` and stores the bin edges, and ``transform`` maps each value to the bin of its nearest
centroid. It works in a ``Pipeline`` and with ``clone``.
"""

import warnings
from typing import Self, TypeAlias, no_type_check

import numpy as np
import numpy.typing as npt
from scipy import sparse
from sklearn.base import BaseEstimator, OneToOneFeatureMixin, TransformerMixin
from sklearn.utils.validation import check_is_fitted, validate_data  # pyrefly: ignore[missing-module-attribute] -- the scikit-learn stubs that pyrefly bundles predate validate_data, which scikit-learn 1.6 added

from optimal_discretizer.core.exceptions import BinCountWarning, ParameterRangeError, ScorerError
from optimal_discretizer.domain.bin_edges import centroids_to_edges
from optimal_discretizer.domain.clustering import Clustering1D, kmeans_1d
from optimal_discretizer.domain.scorers import CandidateFit, NBinsSelector, resolve_scorer

# scikit-learn passes sparse input on to validate_data, which rejects it with the error that the API of scikit-learn
# requires. A hint without the sparse types would make beartype reject it first, with another error.
TrainingData: TypeAlias = npt.ArrayLike | sparse.sparray | sparse.spmatrix


class OptimalDiscretizer(OneToOneFeatureMixin, TransformerMixin, BaseEstimator):
    """Discretize each feature into bins with exact 1-D k-means.

    For each feature, ``fit`` finds the clustering of the values into ``n_bins`` clusters with the smallest sum of
    squared distances to the cluster means (``kmeans_1d``). The bin edges are the midpoints between consecutive
    centroids. ``transform`` replaces each value with the index of its bin: bin 0 holds the smallest values.

    If a feature has fewer distinct values than the number of bins, the feature gets one bin for each distinct value,
    and ``fit`` warns with ``BinCountWarning``.

    Parameters
    ----------
    n_bins: int or None, default=5
        The number of bins of each feature. ``None`` lets ``scorer`` choose the number of each feature from the
        exact clusterings for each number in ``n_bins_range``.
    n_bins_range: tuple of (int, int) or None, default=None
        The smallest and the largest number of bins that ``scorer`` can choose, both included. ``None`` is
        ``(1, number of distinct values)``. The discretizer reads it only when ``n_bins`` is ``None``.
    scorer: str or NBinsSelector or None, default=None
        The rule that chooses the number of bins when ``n_bins`` is ``None``: a name of ``SCORERS``
        (``"second_difference"``, ``"mdl_gaussian"``, ``"mdl_bits_knee"``, ``"kneed_inertia"``) or an object with a
        ``select(values, candidates)`` method, such as ``MaxScore(score_function)``. The rules are heuristics: each
        candidate clustering is exact, but the chosen number of bins is not optimal in any proved sense.

    Attributes
    ----------
    centroids_: list of numpy.ndarray of float64
        The centroids of the bins of each feature, in increasing order.
    bin_edges_: list of numpy.ndarray of float64
        The edges of the bins of each feature: the midpoints between consecutive centroids, with ``-inf`` and ``+inf``
        at the ends.
    n_bins_: numpy.ndarray of int64, shape (n_features,)
        The number of bins of each feature.
    inertia_: numpy.ndarray of float64, shape (n_features,)
        The sum of squared distances of the training values of each feature to the centroids of their bins.
    n_features_in_: int
        The number of features of the training data.
    feature_names_in_: numpy.ndarray of str
        The names of the features, if the training data has string column names.

    Examples
    --------
    >>> import numpy as np
    >>> from optimal_discretizer import OptimalDiscretizer
    >>> values = np.array([[1.0], [2.0], [10.0], [11.0], [30.0]])
    >>> discretizer = OptimalDiscretizer(n_bins=3).fit(values)
    >>> discretizer.transform(values).ravel().tolist()
    [0.0, 0.0, 1.0, 1.0, 2.0]
    >>> discretizer.bin_edges_[0].tolist()
    [-inf, 6.0, 20.25, inf]

    """

    n_bins: int | None
    n_bins_range: tuple[int, int] | None
    scorer: str | NBinsSelector | None
    # The fitted attributes. fit sets them; scikit-learn reads the trailing underscore as the sign of a fitted model.
    centroids_: list[npt.NDArray[np.float64]]
    bin_edges_: list[npt.NDArray[np.float64]]
    n_bins_: npt.NDArray[np.int64]
    inertia_: npt.NDArray[np.float64]
    n_features_in_: int

    # scikit-learn requires that __init__ stores any value and that fit validates it, so beartype skips this method.
    @no_type_check
    def __init__(
        self,
        n_bins: int | None = 5,
        n_bins_range: tuple[int, int] | None = None,
        scorer: str | NBinsSelector | None = None,
    ) -> None:
        """Store the parameters. scikit-learn checks them in ``fit``, not here.

        Parameters
        ----------
        n_bins: int or None
            See the class docstring.
        n_bins_range: tuple of (int, int) or None
            See the class docstring.
        scorer: str or NBinsSelector or None
            See the class docstring.

        """
        self.n_bins = n_bins
        self.n_bins_range = n_bins_range
        self.scorer = scorer

    def _cluster_feature(self, values: npt.NDArray[np.float64], distinct_count: int) -> CandidateFit:
        """Return the clustering of one feature for the fixed or the chosen number of bins.

        Parameters
        ----------
        values: numpy.ndarray of float64, shape (n_samples,)
            The values of the feature.
        distinct_count: int
            The number of distinct values. No feature gets more bins than this.

        Returns
        -------
        CandidateFit
            The number of bins and the clustering.

        Raises
        ------
        ParameterRangeError
            If ``n_bins`` or ``n_bins_range`` is outside the allowed range.
        ScorerError
            If ``n_bins`` is ``None`` and ``scorer`` is ``None``, or if the scorer returns a number of bins that it
            was not given.

        """
        if self.n_bins is not None:
            if self.n_bins < 1:
                raise ParameterRangeError(name="n_bins", value=self.n_bins, allowed="at least 1")
            bin_count = min(self.n_bins, distinct_count)
            return CandidateFit(n_bins=bin_count, clustering=kmeans_1d(values, bin_count))
        if self.scorer is None:
            msg = "scorer must be set when n_bins is None, for example scorer='mdl_bits_knee'"
            raise ScorerError(msg)
        smallest, largest = self.n_bins_range if self.n_bins_range is not None else (1, distinct_count)
        if smallest < 1:
            raise ParameterRangeError(name="n_bins_range[0]", value=smallest, allowed="at least 1")
        if largest < smallest:
            raise ParameterRangeError(name="n_bins_range[1]", value=largest, allowed=f"at least {smallest}")
        largest = min(largest, distinct_count)
        smallest = min(smallest, largest)
        candidates = [
            CandidateFit(n_bins=bin_count, clustering=kmeans_1d(values, bin_count))
            for bin_count in range(smallest, largest + 1)
        ]
        chosen = resolve_scorer(self.scorer).select(values, candidates)
        for candidate in candidates:
            if candidate.n_bins == chosen:
                return candidate
        msg = f"the scorer chose n_bins={chosen}, which is not between {smallest} and {largest}"
        raise ScorerError(msg)

    def fit(self, X: TrainingData, y: npt.ArrayLike | None = None) -> Self:  # ruff: ignore[invalid-argument-name] -- scikit-learn names the training data X in every estimator
        """Find the bins of each feature.

        Parameters
        ----------
        X: array-like of shape (n_samples, n_features)
            The training data. NaN and infinite values raise ``ValueError``.
        y: None
            Ignored. The parameter exists for the API of scikit-learn.

        Returns
        -------
        OptimalDiscretizer
            The fitted discretizer.

        Warns
        -----
        BinCountWarning
            If a feature has fewer distinct values than ``n_bins`` or the top of ``n_bins_range``.

        """
        del y
        data = validate_data(self, X, dtype=np.float64)
        fits: list[CandidateFit] = []
        reduced_features: list[int] = []
        for feature_index in range(data.shape[1]):
            values = np.ascontiguousarray(data[:, feature_index])
            distinct_count = np.unique(values).size
            requested = self.n_bins if self.n_bins is not None else (self.n_bins_range or (1, distinct_count))[1]
            if requested > distinct_count:
                reduced_features.append(feature_index)
            fits.append(self._cluster_feature(values, distinct_count))
        if reduced_features:
            warnings.warn(
                f"features {reduced_features} have fewer distinct values than the requested number of bins; "
                "each of them gets one bin for each distinct value",
                BinCountWarning,
                stacklevel=2,
            )
        clusterings: list[Clustering1D] = [fit.clustering for fit in fits]
        self.centroids_ = [clustering.centroids for clustering in clusterings]
        self.bin_edges_ = [centroids_to_edges(centroids) for centroids in self.centroids_]
        self.n_bins_ = np.array([fit.n_bins for fit in fits], dtype=np.int64)
        self.inertia_ = np.array([clustering.inertia for clustering in clusterings], dtype=np.float64)
        return self

    def transform(self, X: TrainingData) -> npt.NDArray[np.float64]:  # ruff: ignore[invalid-argument-name] -- scikit-learn names the input data X in every estimator
        """Replace each value with the index of its bin.

        Parameters
        ----------
        X: array-like of shape (n_samples, n_features)
            The data. It must have the features of the training data. NaN and infinite values raise ``ValueError``.

        Returns
        -------
        numpy.ndarray of float64, shape (n_samples, n_features)
            The bin of each value, from 0 to ``n_bins_[feature] - 1``.

        """
        check_is_fitted(self)
        data = validate_data(self, X, dtype=np.float64, reset=False)
        bins = np.empty_like(data)
        for feature_index, edges in enumerate(self.bin_edges_):
            bins[:, feature_index] = np.searchsorted(edges[1:-1], data[:, feature_index], side="right")
        return bins
