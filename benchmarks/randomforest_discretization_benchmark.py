"""Benchmark RandomForest quality and speed under four discretization variants.

Variants
--------
none      -- RandomForest on raw features (baseline).
quantile  -- KBinsDiscretizer(strategy="quantile", encode="ordinal") + RF.
kmeans    -- KBinsDiscretizer(strategy="kmeans",   encode="ordinal") + RF.
optimal   -- OptimalDiscretizer (this package's exact 1-D k-means)   + RF.

Sweeps over ``n_bins`` {2, 4, 8, 16, 32, 64} and a small RF hyper-parameter
grid {n_estimators: [100, 300], max_depth: [None, 12]}, using repeated K-fold
cross-validation so all variants share identical folds.

Run with::

    uv run python benchmarks/randomforest_discretization_benchmark.py --repeats 3
"""

import datetime as dt
import hashlib
import importlib.metadata
import platform
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias

import attrs
import cyclopts
import numpy as np
import sklearn
from sklearn.datasets import (
    fetch_california_housing,
    load_breast_cancer,
    load_diabetes,
    load_wine,
    make_classification,
    make_regression,
)
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import f1_score, mean_squared_error, r2_score, roc_auc_score
from sklearn.model_selection import RepeatedKFold, RepeatedStratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import KBinsDiscretizer

from benchmarks.run_files import append_jsonl, dumps, resolve_git_commit
from optimal_discretizer import OptimalDiscretizer

try:
    _PKG_VERSION = importlib.metadata.version("optimal-discretizer")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "unknown"

DEFAULT_REPEATS = 3
DEFAULT_OUTPUT = Path(".benchmarks/randomforest_discretization_runs.jsonl")
DEFAULT_N_BINS = [2, 4, 8, 16, 32, 64]
DEFAULT_N_ESTIMATORS = [100, 300]
DEFAULT_MAX_DEPTHS: list[int | None] = [None, 12]
DEFAULT_N_JOBS = 1
DEFAULT_CV_FOLDS = 5
DEFAULT_CV_REPEATS = 2
DEFAULT_SEED = 42

Variant: TypeAlias = Literal["none", "quantile", "kmeans", "optimal"]
VARIANTS: list[Variant] = ["none", "quantile", "kmeans", "optimal"]
# A binary classifier reports the area under the ROC curve from the probability of the second class.
_BINARY_CLASS_COUNT = 2


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------


@attrs.frozen
class DatasetConfig:
    """Describes one benchmark dataset."""

    name: str
    task: str  # "classification" or "regression"


# Registry of all supported dataset names and their task types.
DATASET_REGISTRY: dict[str, str] = {
    "breast_cancer": "classification",
    "wine": "classification",
    "synth_clf": "classification",
    "diabetes": "regression",
    "california_housing": "regression",
    "synth_reg": "regression",
}


def load_single_dataset(name: str) -> tuple[np.ndarray, np.ndarray, str]:
    """Load one dataset by name and return ``(X, y, task)``.

    Parameters
    ----------
    name : str
        Dataset name from ``DATASET_REGISTRY``.

    Returns
    -------
    tuple of (ndarray, ndarray, str)
        Feature matrix, target vector, and task type.

    Raises
    ------
    ValueError
        If ``name`` is not in ``DATASET_REGISTRY``.

    """
    if name == "breast_cancer":
        ds = load_breast_cancer()
        return ds.data, ds.target, "classification"
    if name == "wine":
        ds = load_wine()
        return ds.data, ds.target, "classification"
    if name == "synth_clf":
        features, target = make_classification(
            n_samples=600,
            n_features=20,
            n_informative=10,
            n_redundant=4,
            n_classes=2,
            random_state=DEFAULT_SEED,
        )
        return features, target, "classification"
    if name == "diabetes":
        ds = load_diabetes()
        return ds.data, ds.target, "regression"
    if name == "california_housing":
        ds = fetch_california_housing()
        return ds.data, ds.target, "regression"
    if name == "synth_reg":
        features, target = make_regression(
            n_samples=600,
            n_features=20,
            n_informative=10,
            noise=0.1,
            random_state=DEFAULT_SEED,
        )
        return features, target, "regression"
    msg = f"Unknown dataset {name!r}. Available: {sorted(DATASET_REGISTRY)}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Pipeline builders
# ---------------------------------------------------------------------------


@attrs.frozen(kw_only=True)
class ForestConfig:
    """One point of the grid: a discretization variant and the settings of the forest.

    Attributes
    ----------
    variant : str
        One of ``none``, ``quantile``, ``kmeans``, ``optimal``.
    n_bins : int
        Number of bins of the discretizer. ``variant="none"`` ignores it.
    n_estimators : int
        Number of trees in the forest.
    max_depth : int or None
        Maximum depth of each tree.

    """

    variant: Variant
    n_bins: int
    n_estimators: int
    max_depth: int | None


@attrs.frozen(kw_only=True)
class Dataset:
    """One loaded dataset.

    Attributes
    ----------
    name : str
        The name in ``DATASET_REGISTRY``.
    features : ndarray
        The feature matrix.
    target : ndarray
        The target vector.
    task : str
        ``"classification"`` or ``"regression"``.

    """

    name: str
    features: np.ndarray
    target: np.ndarray
    task: str


DISCRETIZERS: Mapping[str, Callable[[int], KBinsDiscretizer | OptimalDiscretizer]] = {
    "quantile": lambda n_bins: KBinsDiscretizer(n_bins=n_bins, strategy="quantile", encode="ordinal", subsample=None),
    "kmeans": lambda n_bins: KBinsDiscretizer(n_bins=n_bins, strategy="kmeans", encode="ordinal", subsample=None),
    "optimal": lambda n_bins: OptimalDiscretizer(n_bins=n_bins),
}
"""The discretizer of each variant, by name. The variant ``none`` has no discretizer."""


def build_forest(config: ForestConfig, task: str, seed: int) -> RandomForestClassifier | RandomForestRegressor:
    """Build the forest of a config for the task.

    Parameters
    ----------
    config : ForestConfig
        The settings of the forest.
    task : str
        ``"classification"`` or ``"regression"``.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    RandomForestClassifier or RandomForestRegressor
        The unfitted forest.

    """
    forest_class = RandomForestClassifier if task == "classification" else RandomForestRegressor
    return forest_class(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        random_state=seed,
        n_jobs=DEFAULT_N_JOBS,
    )


def build_pipeline(config: ForestConfig, task: str, seed: int) -> Pipeline:
    """Build the pipeline of a config: the discretizer of its variant, if any, then the forest.

    Parameters
    ----------
    config : ForestConfig
        The variant and the settings of the forest.
    task : str
        ``"classification"`` or ``"regression"``.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    Pipeline
        The unfitted pipeline.

    Raises
    ------
    ValueError
        If the variant is not ``none`` and not in ``DISCRETIZERS``.

    """
    forest = build_forest(config, task, seed)
    if config.variant == "none":
        return Pipeline([("rf", forest)])
    if config.variant not in DISCRETIZERS:
        msg = f"Unknown variant {config.variant!r}."
        raise ValueError(msg)
    return Pipeline([("disc", DISCRETIZERS[config.variant](config.n_bins)), ("rf", forest)])


# ---------------------------------------------------------------------------
# Cross-validation evaluation
# ---------------------------------------------------------------------------


def _classification_quality(
    forest: RandomForestClassifier,
    test_features: np.ndarray,
    test_target: np.ndarray,
    predicted: np.ndarray,
) -> dict[
    str,
    float,
]:
    """Return the area under the ROC curve, the accuracy and the macro F1 score of one fold.

    Returns
    -------
    dict
        The metrics by name.

    """
    probabilities = forest.predict_proba(test_features)
    if probabilities.shape[1] == _BINARY_CLASS_COUNT:
        roc_auc = float(roc_auc_score(test_target, probabilities[:, 1]))
    else:
        roc_auc = float(roc_auc_score(test_target, probabilities, multi_class="ovr", average="macro"))
    return {
        "roc_auc": roc_auc,
        "accuracy": float((predicted == test_target).mean()),
        "macro_f1": float(f1_score(test_target, predicted, average="macro", zero_division=0)),
    }


def _regression_quality(
    forest: RandomForestRegressor,
    test_features: np.ndarray,
    test_target: np.ndarray,
    predicted: np.ndarray,
) -> dict[
    str,
    float,
]:
    """Return the R2 score and the root mean squared error of one fold.

    Returns
    -------
    dict
        The metrics by name.

    """
    del forest, test_features
    return {
        "r2": float(r2_score(test_target, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(test_target, predicted))),
    }


QUALITY: Mapping[str, Callable[..., dict[str, float]]] = {
    "classification": _classification_quality,
    "regression": _regression_quality,
}
"""The quality metrics of each task, by task name."""


def _run_fold(
    pipe: Pipeline,
    dataset: Dataset,
    train_index: np.ndarray,
    test_index: np.ndarray,
) -> dict[
    str,
    float,
]:
    """Fit and time the discretizer and the forest on one fold, and measure the quality on its test part.

    Returns
    -------
    dict
        The times and the quality metrics of the fold, by name.

    """
    train_features, test_features = dataset.features[train_index], dataset.features[test_index]
    train_target, test_target = dataset.target[train_index], dataset.target[test_index]
    disc_fit_time = disc_transform_time = 0.0
    if "disc" in pipe.named_steps:
        discretizer = pipe.named_steps["disc"]
        started = time.perf_counter()
        train_features = discretizer.fit(train_features).transform(train_features)
        disc_fit_time = time.perf_counter() - started
        started = time.perf_counter()
        test_features = discretizer.transform(test_features)
        disc_transform_time = time.perf_counter() - started
    forest = pipe.named_steps["rf"]
    started = time.perf_counter()
    forest.fit(train_features, train_target)
    rf_fit_time = time.perf_counter() - started
    started = time.perf_counter()
    predicted = forest.predict(test_features)
    rf_predict_time = time.perf_counter() - started
    return {
        "disc_fit_time": disc_fit_time,
        "disc_transform_time": disc_transform_time,
        "rf_fit_time": rf_fit_time,
        "rf_predict_time": rf_predict_time,
        "total_time": disc_fit_time + disc_transform_time + rf_fit_time + rf_predict_time,
        **QUALITY[dataset.task](forest, test_features, test_target, predicted),
    }


def evaluate_config(
    config: ForestConfig,
    dataset: Dataset,
    seed: int,
    cv_repeats: int,
) -> dict[
    str,
    float,
]:
    """Evaluate one config on one dataset with repeated K-fold cross-validation.

    Parameters
    ----------
    config : ForestConfig
        The variant and the settings of the forest.
    dataset : Dataset
        The data.
    seed : int
        Base random seed; the seed of each fold derives from it.
    cv_repeats : int
        Number of repeats of the cross-validation.

    Returns
    -------
    dict
        The mean and the standard deviation over the folds of each metric, as ``<metric>_mean`` and ``<metric>_std``.

    """
    splitter_class = RepeatedStratifiedKFold if dataset.task == "classification" else RepeatedKFold
    splitter = splitter_class(n_splits=DEFAULT_CV_FOLDS, n_repeats=cv_repeats, random_state=seed)
    fold_metrics = [
        _run_fold(build_pipeline(config, dataset.task, seed + fold_offset), dataset, train_index, test_index)
        for fold_offset, (train_index, test_index) in enumerate(splitter.split(dataset.features, dataset.target))
    ]
    aggregated: dict[str, float] = {}
    for metric in fold_metrics[0]:
        values = [fold[metric] for fold in fold_metrics]
        aggregated[f"{metric}_mean"] = float(np.mean(values))
        aggregated[f"{metric}_std"] = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return aggregated


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def config_seed(dataset_name: str, config: ForestConfig, base_seed: int) -> int:
    """Derive a stable seed for one config of one dataset from the base seed.

    Returns
    -------
    int
        The seed.

    """
    key = f"{dataset_name}:{config.variant}:{config.n_bins}:{config.n_estimators}:{config.max_depth}"
    digest = int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    return base_seed + (digest % (2**16))


def run_one_config(
    dataset: Dataset,
    config: ForestConfig,
    base_seed: int,
    cv_repeats: int,
) -> dict[
    str,
    Any,
]:
    """Evaluate one config and return the row of the JSONL file.

    Returns
    -------
    dict
        The config, its seed and its metrics.

    """
    seed = config_seed(dataset.name, config, base_seed)
    return {
        "dataset": dataset.name,
        "task": dataset.task,
        "variant": config.variant,
        "n_bins": config.n_bins if config.variant != "none" else None,
        "n_estimators": config.n_estimators,
        "max_depth": config.max_depth,
        "seed": seed,
        **evaluate_config(config, dataset, seed, cv_repeats),
    }


def grid_configs(n_bins_list: Sequence[int], variants: Sequence[Variant]) -> list[ForestConfig]:
    """Return every config of the grid. The variant ``none`` runs once, because it does not read ``n_bins``.

    Parameters
    ----------
    n_bins_list : Sequence of int
        Bin counts to sweep.
    variants : Sequence of str
        Variant names to include.

    Returns
    -------
    list of ForestConfig
        The configs.

    """
    return [
        ForestConfig(variant=variant, n_bins=n_bins, n_estimators=n_estimators, max_depth=max_depth)
        for n_bins in n_bins_list
        for n_estimators in DEFAULT_N_ESTIMATORS
        for max_depth in DEFAULT_MAX_DEPTHS
        for variant in variants
        if variant != "none" or n_bins == n_bins_list[0]
    ]


def _progress_line(row: dict[str, Any], completed: int, total_configs: int) -> str:
    """Return the progress line of one evaluated config.

    Returns
    -------
    str
        The line, with the main quality metric and the total time.

    """
    quality = f"roc_auc={row['roc_auc_mean']:.4f}" if row["task"] == "classification" else f"r2={row['r2_mean']:.4f}"
    n_bins = row["n_bins"] if row["n_bins"] is not None else 0
    return (
        f"  [{completed}/{total_configs}] {row['variant']:10s} n_bins={n_bins:3d} est={row['n_estimators']:4d} "
        f"depth={row['max_depth']!s:4s}  {quality}  total_time={row['total_time_mean']:.3f}s\n"
    )


def _run_metadata(
    repeats: int,
    seed: int,
    n_bins: Sequence[int],
) -> dict[
    str,
    Any,
]:
    """Return the fields that describe the run and its environment.

    Returns
    -------
    dict
        The metadata of the run.

    """
    return {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "commit": resolve_git_commit(Path(__file__).resolve().parent.parent),
        "repeats": repeats,
        "cv_folds": DEFAULT_CV_FOLDS,
        "cv_repeats": repeats,
        "seed": seed,
        "n_bins_sweep": list(n_bins),
        "n_estimators_grid": DEFAULT_N_ESTIMATORS,
        "max_depth_grid": DEFAULT_MAX_DEPTHS,
        "n_jobs": DEFAULT_N_JOBS,
        "timing_method": "time.perf_counter; mean over folds x repeats reported",
        "platform": platform.platform(),
        "python_version": sys.version,
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "package_version": _PKG_VERSION,
    }


app: cyclopts.App = cyclopts.App(
    name="randomforest_discretization_benchmark",
    help=__doc__.splitlines()[0] if __doc__ else None,
    result_action="return_value",
)


@cyclopts.Parameter(name="*")
@attrs.frozen(kw_only=True)
class BenchmarkOptions:
    """The options of the command line.

    Attributes
    ----------
    repeats : int
        Number of repeats of the cross-validation of each config.
    datasets : list of str or None
        The datasets to run. ``None`` runs every dataset of ``DATASET_REGISTRY``.
    n_bins : list of int
        The bin counts to sweep.
    variants : list of str
        The discretization variants to benchmark.
    seed : int
        Base random seed.
    output : Path
        The JSONL file that the run is appended to.

    """

    repeats: int = DEFAULT_REPEATS
    datasets: Annotated[list[str] | None, cyclopts.Parameter(consume_multiple=True)] = None
    n_bins: Annotated[list[int], cyclopts.Parameter(consume_multiple=True)] = attrs.Factory(
        lambda: list(DEFAULT_N_BINS),
    )
    variants: Annotated[list[Variant], cyclopts.Parameter(consume_multiple=True)] = attrs.Factory(
        lambda: list(VARIANTS),
    )
    seed: int = DEFAULT_SEED
    output: Path = DEFAULT_OUTPUT


@app.default
def main(options: BenchmarkOptions | None = None) -> int:
    """Run the RandomForest discretization benchmark and append the run to a JSONL file.

    Parameters
    ----------
    options : BenchmarkOptions or None
        The options of the command line. ``None`` uses the defaults.

    Returns
    -------
    int
        0 when the run is saved.

    """
    options = options or BenchmarkOptions()
    dataset_names = options.datasets if options.datasets is not None else list(DATASET_REGISTRY)
    configs = grid_configs(options.n_bins, options.variants)
    results: dict[str, list[dict[str, Any]]] = {}
    completed = 0
    for dataset_name in dataset_names:
        if dataset_name not in DATASET_REGISTRY:
            sys.stdout.write(f"Unknown dataset {dataset_name!r}, skipping.\n")
            continue
        try:
            features, target, task = load_single_dataset(dataset_name)
        except (OSError, ValueError) as error:  # california_housing downloads its data, which can fail offline
            sys.stdout.write(f"Failed to load dataset {dataset_name!r}: {error}  Skipping.\n")
            continue
        dataset = Dataset(name=dataset_name, features=features, target=target, task=task)
        sys.stdout.write(f"\nDataset: {dataset_name}  task={task}  shape={features.shape}\n")
        results[dataset_name] = []
        for config in configs:
            completed += 1
            row = run_one_config(dataset, config, options.seed, options.repeats)
            results[dataset_name].append(row)
            sys.stdout.write(_progress_line(row, completed, len(dataset_names) * len(configs)))
            sys.stdout.flush()
    metadata = _run_metadata(options.repeats, options.seed, options.n_bins)
    append_jsonl(options.output, dumps({**metadata, "results": results}))
    sys.stdout.write(f"\nSaved run to {options.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(app())
