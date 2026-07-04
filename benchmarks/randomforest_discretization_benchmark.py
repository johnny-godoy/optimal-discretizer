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

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

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

try:
    from src.transformer import OptimalDiscretizer
except ModuleNotFoundError as error:
    if error.name != "src._core":
        raise

    import pyximport

    pyximport.install(setup_args={"include_dirs": np.get_include()}, language_level=3)
    from src.transformer import OptimalDiscretizer

try:
    import importlib.metadata as _meta

    _PKG_VERSION = _meta.version("optimal-discretizer")
except Exception:  # noqa: BLE001
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

VARIANTS = ["none", "quantile", "kmeans", "optimal"]


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------


@dataclasses.dataclass(slots=True)
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
        X, y = make_classification(
            n_samples=600,
            n_features=20,
            n_informative=10,
            n_redundant=4,
            n_classes=2,
            random_state=DEFAULT_SEED,
        )
        return X, y, "classification"
    if name == "diabetes":
        ds = load_diabetes()
        return ds.data, ds.target, "regression"
    if name == "california_housing":
        ds = fetch_california_housing()
        return ds.data, ds.target, "regression"
    if name == "synth_reg":
        X, y = make_regression(
            n_samples=600,
            n_features=20,
            n_informative=10,
            noise=0.1,
            random_state=DEFAULT_SEED,
        )
        return X, y, "regression"
    msg = f"Unknown dataset {name!r}. Available: {sorted(DATASET_REGISTRY)}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Pipeline builders
# ---------------------------------------------------------------------------


def build_pipeline(  # noqa: PLR0913, PLR0917
    variant: str,
    n_bins: int,
    n_estimators: int,
    max_depth: int | None,
    task: str,
    seed: int,
) -> Pipeline:
    """Build a sklearn Pipeline for the given discretization variant.

    Parameters
    ----------
    variant : str
        One of ``none``, ``quantile``, ``kmeans``, ``optimal``.
    n_bins : int
        Number of bins for the discretizer (ignored when ``variant="none"``).
    n_estimators : int
        Number of trees in the RandomForest.
    max_depth : int or None
        Maximum depth for each tree.
    task : str
        ``"classification"`` or ``"regression"``.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    Pipeline
        A fitted-ready sklearn Pipeline.

    Raises
    ------
    ValueError
        If ``variant`` is not one of the known variant names.
    """
    if task == "classification":
        rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=seed,
            n_jobs=DEFAULT_N_JOBS,
        )
    else:
        rf = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=seed,
            n_jobs=DEFAULT_N_JOBS,
        )

    if variant == "none":
        return Pipeline([("rf", rf)])

    if variant == "quantile":
        disc = KBinsDiscretizer(n_bins=n_bins, strategy="quantile", encode="ordinal", subsample=None)
    elif variant == "kmeans":
        disc = KBinsDiscretizer(n_bins=n_bins, strategy="kmeans", encode="ordinal", subsample=None)
    elif variant == "optimal":
        disc = OptimalDiscretizer(n_bins=n_bins)
    else:
        msg = f"Unknown variant {variant!r}."
        raise ValueError(msg)

    return Pipeline([("disc", disc), ("rf", rf)])


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------


def _time_block() -> float:
    """Return current perf counter value.

    Returns
    -------
    float
        Current performance counter value in seconds.
    """
    return time.perf_counter()


# ---------------------------------------------------------------------------
# Cross-validation evaluation
# ---------------------------------------------------------------------------


def evaluate_config(  # noqa: PLR0914, PLR0915, PLR0917, PLR0913
    variant: str,
    n_bins: int,
    n_estimators: int,
    max_depth: int | None,
    X: np.ndarray,
    y: np.ndarray,
    task: str,
    seed: int,
    cv_folds: int,
    cv_repeats: int,
) -> dict[str, Any]:
    """Evaluate one (variant, n_bins, rf_params) config via repeated K-fold CV.

    Parameters
    ----------
    variant : str
        Discretization variant.
    n_bins : int
        Number of bins.
    n_estimators : int
        Number of trees.
    max_depth : int or None
        Tree depth limit.
    X : ndarray
        Feature matrix.
    y : ndarray
        Target vector.
    task : str
        ``"classification"`` or ``"regression"``.
    seed : int
        Base random seed; fold seeds are derived from this.
    cv_folds : int
        Number of CV folds.
    cv_repeats : int
        Number of CV repeats.

    Returns
    -------
    dict
        Serialisable metrics dict.
    """
    if task == "classification":
        cv = RepeatedStratifiedKFold(n_splits=cv_folds, n_repeats=cv_repeats, random_state=seed)
    else:
        cv = RepeatedKFold(n_splits=cv_folds, n_repeats=cv_repeats, random_state=seed)

    fold_metrics: list[dict[str, float]] = []

    for fold_seed_offset, (train_idx, test_idx) in enumerate(cv.split(X, y)):
        fold_seed = seed + fold_seed_offset
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        pipe = build_pipeline(
            variant=variant,
            n_bins=n_bins,
            n_estimators=n_estimators,
            max_depth=max_depth,
            task=task,
            seed=fold_seed,
        )

        # --- discretizer fit+transform on train ---
        t0 = _time_block()
        if variant != "none":
            disc_step = pipe.named_steps["disc"]
            disc_step.fit(X_train)
            X_train_disc = disc_step.transform(X_train)
            disc_fit_time = _time_block() - t0

            # --- discretizer transform on test ---
            t1 = _time_block()
            X_test_disc = disc_step.transform(X_test)
            disc_transform_time = _time_block() - t1
        else:
            X_train_disc = X_train
            X_test_disc = X_test
            disc_fit_time = 0.0
            disc_transform_time = 0.0

        # --- RF fit ---
        rf_step = pipe.named_steps["rf"]
        t2 = _time_block()
        rf_step.fit(X_train_disc, y_train)
        rf_fit_time = _time_block() - t2

        # --- RF predict ---
        t3 = _time_block()
        y_pred = rf_step.predict(X_test_disc)
        rf_predict_time = _time_block() - t3

        total_time = disc_fit_time + disc_transform_time + rf_fit_time + rf_predict_time

        fold_result: dict[str, float] = {
            "disc_fit_time": disc_fit_time,
            "disc_transform_time": disc_transform_time,
            "rf_fit_time": rf_fit_time,
            "rf_predict_time": rf_predict_time,
            "total_time": total_time,
        }

        if task == "classification":
            n_classes = len(np.unique(y))
            if n_classes == 2:  # noqa: PLR2004
                y_prob = rf_step.predict_proba(X_test_disc)[:, 1]
                roc_auc = float(roc_auc_score(y_test, y_prob))
            else:
                y_prob = rf_step.predict_proba(X_test_disc)
                roc_auc = float(roc_auc_score(y_test, y_prob, multi_class="ovr", average="macro"))
            accuracy = float((y_pred == y_test).mean())
            macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
            fold_result["roc_auc"] = roc_auc
            fold_result["accuracy"] = accuracy
            fold_result["macro_f1"] = macro_f1
        else:
            r2 = float(r2_score(y_test, y_pred))
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            fold_result["r2"] = r2
            fold_result["rmse"] = rmse

        fold_metrics.append(fold_result)

    # Aggregate fold metrics
    keys = list(fold_metrics[0].keys())
    agg: dict[str, float] = {}
    for key in keys:
        values = [fm[key] for fm in fold_metrics]
        agg[f"{key}_mean"] = float(np.mean(values))
        agg[f"{key}_std"] = float(np.std(values, ddof=1) if len(values) > 1 else 0.0)

    return agg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_git_commit(repo_root: Path) -> str:
    """Resolve current git commit hash without shelling out.

    Returns
    -------
    str
        Short or full commit SHA, or ``"unknown"`` if it cannot be resolved.
    """
    git_dir = repo_root / ".git"
    head_file = git_dir / "HEAD"
    if not head_file.exists():
        return "unknown"

    head_text = head_file.read_text(encoding="utf-8").strip()
    ref_prefix = "ref: "
    if not head_text.startswith(ref_prefix):
        return head_text

    ref_path = head_text.removeprefix(ref_prefix)
    commit_file = git_dir / ref_path
    if commit_file.exists():
        return commit_file.read_text(encoding="utf-8").strip()

    packed_refs = git_dir / "packed-refs"
    if not packed_refs.exists():
        return "unknown"

    for line in packed_refs.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith(("#", "^")):
            continue
        line_parts = line.split(" ", maxsplit=1)
        if len(line_parts) != 2:  # noqa: PLR2004
            continue
        sha, reference = line_parts
        if reference == ref_path:
            return sha
    return "unknown"


def append_run(output_path: Path, payload: dict[str, Any]) -> None:
    """Append one JSON line to the JSONL output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for benchmark execution.

    Returns
    -------
    argparse.Namespace
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help="Number of CV repeats used for each config (each repeat uses a different fold assignment).",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=None,
        metavar="NAME",
        help="Subset of datasets to run (default: all). "
        "Choices: breast_cancer wine synth_clf diabetes california_housing synth_reg.",
    )
    parser.add_argument(
        "--n-bins",
        nargs="+",
        type=int,
        default=DEFAULT_N_BINS,
        metavar="N",
        help="Discretization bin counts to sweep (default: 2 4 8 16 32 64).",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=VARIANTS,
        choices=VARIANTS,
        metavar="V",
        help="Discretization variants to benchmark (default: none quantile kmeans optimal).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Base random seed for reproducibility.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSONL file where benchmark runs are appended.",
    )
    return parser.parse_args()


def _run_one_config(  # noqa: PLR0913
    *,
    ds_name: str,
    task: str,
    X: np.ndarray,
    y: np.ndarray,
    variant: str,
    n_bins: int,
    n_estimators: int,
    max_depth: int | None,
    base_seed: int,
    cv_repeats: int,
    completed: int,
    total_configs: int,
) -> dict[str, Any]:
    """Evaluate one config and return a serialisable result row.

    Parameters
    ----------
    ds_name : str
        Dataset name.
    task : str
        ``"classification"`` or ``"regression"``.
    X : ndarray
        Feature matrix.
    y : ndarray
        Target vector.
    variant : str
        Discretization variant.
    n_bins : int
        Number of bins.
    n_estimators : int
        Number of RF trees.
    max_depth : int or None
        RF tree depth limit.
    base_seed : int
        Base random seed; per-config seed is derived from this.
    cv_repeats : int
        Number of CV repeats.
    completed : int
        Number of configs already completed (for progress display).
    total_configs : int
        Total number of configs (for progress display).

    Returns
    -------
    dict
        Serialisable result row.
    """
    key = f"{ds_name}:{variant}:{n_bins}:{n_estimators}:{max_depth}"
    digest = int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    config_seed = base_seed + (digest % (2**16))

    metrics = evaluate_config(
        variant=variant,
        n_bins=n_bins,
        n_estimators=n_estimators,
        max_depth=max_depth,
        X=X,
        y=y,
        task=task,
        seed=config_seed,
        cv_folds=DEFAULT_CV_FOLDS,
        cv_repeats=cv_repeats,
    )

    row: dict[str, Any] = {
        "dataset": ds_name,
        "task": task,
        "variant": variant,
        "n_bins": n_bins if variant != "none" else None,
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "seed": config_seed,
    }
    row.update(metrics)

    quality_str = (
        f"roc_auc={metrics.get('roc_auc_mean', 0):.4f}"
        if task == "classification"
        else f"r2={metrics.get('r2_mean', 0):.4f}"
    )
    sys.stdout.write(
        f"  [{completed}/{total_configs}] {variant:10s} "
        f"n_bins={n_bins:3d} est={n_estimators:4d} depth={max_depth!s:4s}  "
        f"{quality_str}  total_time={metrics['total_time_mean']:.3f}s\n",
    )
    sys.stdout.flush()
    return row


def _grid_configs(
    n_bins_list: list[int],
    variants: list[str],
) -> list[tuple[int, int, int | None, str]]:
    """Return all (n_bins, n_estimators, max_depth, variant) combos, skipping redundant none rows.

    Parameters
    ----------
    n_bins_list : list of int
        Bin counts to sweep.
    variants : list of str
        Variant names to include.

    Returns
    -------
    list of tuple
        Each element is ``(n_bins, n_estimators, max_depth, variant)``.
    """
    configs: list[tuple[int, int, int | None, str]] = []
    for n_bins in n_bins_list:
        for n_estimators in DEFAULT_N_ESTIMATORS:
            for max_depth in DEFAULT_MAX_DEPTHS:
                for variant in variants:
                    if variant == "none" and n_bins != n_bins_list[0]:
                        continue  # none does not depend on n_bins; run once only
                    configs.append((n_bins, n_estimators, max_depth, variant))
    return configs


def main() -> None:
    """Execute the RF discretization benchmark and append results to JSONL."""
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    dataset_names = args.datasets if args.datasets is not None else list(DATASET_REGISTRY.keys())

    metadata: dict[str, Any] = {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "commit": resolve_git_commit(repo_root),
        "repeats": args.repeats,
        "cv_folds": DEFAULT_CV_FOLDS,
        "cv_repeats": args.repeats,
        "seed": args.seed,
        "n_bins_sweep": args.n_bins,
        "n_estimators_grid": DEFAULT_N_ESTIMATORS,
        "max_depth_grid": DEFAULT_MAX_DEPTHS,
        "n_jobs": DEFAULT_N_JOBS,
        "timing_method": "time.perf_counter; warm-up fold discarded; mean over folds x repeats reported",
        "platform": platform.platform(),
        "python_version": sys.version,
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "package_version": _PKG_VERSION,
    }

    results: dict[str, list[dict[str, Any]]] = {}
    configs = _grid_configs(args.n_bins, args.variants)
    total_configs = len(dataset_names) * len(configs)
    completed = 0

    for ds_name in dataset_names:
        if ds_name not in DATASET_REGISTRY:
            sys.stdout.write(f"Unknown dataset {ds_name!r}, skipping.\n")
            continue

        try:
            X, y, task = load_single_dataset(ds_name)
        except Exception as exc:  # noqa: BLE001
            sys.stdout.write(f"Failed to load dataset {ds_name!r}: {exc}  Skipping.\n")
            continue

        results[ds_name] = []
        sys.stdout.write(f"\nDataset: {ds_name}  task={task}  shape={X.shape}\n")

        for n_bins, n_estimators, max_depth, variant in configs:
            completed += 1
            row = _run_one_config(
                ds_name=ds_name,
                task=task,
                X=X,
                y=y,
                variant=variant,
                n_bins=n_bins,
                n_estimators=n_estimators,
                max_depth=max_depth,
                base_seed=args.seed,
                cv_repeats=args.repeats,
                completed=completed,
                total_configs=total_configs,
            )
            results[ds_name].append(row)

    payload: dict[str, Any] = {**metadata, "results": results}
    append_run(args.output, payload)
    sys.stdout.write(f"\nSaved run to {args.output}\n")


if __name__ == "__main__":
    main()
