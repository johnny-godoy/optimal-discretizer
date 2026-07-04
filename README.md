# optimal-discretizer
An optimal 1-D K-means discretizer compatible with Scikit-Learn

## Overview

`optimal-discretizer` provides an exact, globally optimal 1-D K-means
discretizer implemented in Cython for speed.  It wraps the algorithm
described in

> Grønlund, A., Larsen, K. G., Mathiasen, A., Nielsen, J. S., Schneider, S., & Song, M. (2017).
> *Fast Exact k-Means, k-Medians and Bregman Divergence Clustering in 1D*.
> <https://arxiv.org/abs/1701.07204>

The core of the implementation is the **SMAWK** totally-monotone matrix
searching algorithm, which reduces the per-cluster dynamic programming step
from O(n²) to O(n), giving an overall time complexity of **O(kn log n)**.

## Installation

The project uses [uv](https://docs.astral.sh/uv/) for package management.

```bash
# Install uv if not already available
pip install uv

# Install package (builds the Cython extension automatically)
uv pip install -e ".[dev]"
```

Or with plain pip:

```bash
pip install -e ".[dev]"
```

## Quick start

```python
import numpy as np
from optimal_discretizer import OptimalDiscretizer

rng = np.random.default_rng(0)
X = rng.normal(size=(200, 3))

disc = OptimalDiscretizer(n_bins=5)
X_disc = disc.fit_transform(X)   # shape (200, 3), values in {0,1,2,3,4}

print(disc.centroids_[0])   # centroid of each bin for column 0
print(disc.bin_edges_[0])   # bin-edge thresholds for column 0
```

`OptimalDiscretizer` follows the full [scikit-learn transformer
API](https://scikit-learn.org/stable/data_transforms.html) and can be used
inside a `Pipeline`:

```python
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression

pipe = Pipeline([
    ("disc", OptimalDiscretizer(n_bins=10)),
    ("clf",  LogisticRegression()),
])
pipe.fit(X_train, y_train)
```

## Running tests

```bash
uv run pytest tests/
```

## Benchmarking k-means effectiveness

The project includes a benchmark system that compares:

- `main`: `OptimalDiscretizer` (exact 1-D optimum algorithm)
- `lloyd`: scikit-learn `KMeans(algorithm="lloyd")`
- `bruteforce`: exhaustive partition search (ground-truth optimum)

Run a benchmark suite and append the run to JSONL:

```bash
python benchmarks/kmeans_effectiveness_benchmark.py --repeats 8
```

This writes runs to `.benchmarks/kmeans_effectiveness_runs.jsonl`.

Generate comparison summaries and HTML reports:

```bash
python benchmarks/kmeans_effectiveness_compare.py --plots
```

Reports are written to `.benchmarks/reports/`:

- `kmeans_main_speed_trend.html`
- `kmeans_optimality_trend.html`
- `kmeans_latest_gap_breakdown.html`

If `plotly` is unavailable, the comparison command still prints textual summaries.

## Benchmarking RandomForest discretization (speed vs. quality)

The project includes a second benchmark suite that measures how pre-discretizing
features affects RandomForest **quality** and **speed** across four variants:

- `none`     — RandomForest on raw (undiscretized) features (baseline).
- `quantile` — `KBinsDiscretizer(strategy="quantile", encode="ordinal")` + RF.
- `kmeans`   — `KBinsDiscretizer(strategy="kmeans", encode="ordinal")` + RF.
- `optimal`  — `OptimalDiscretizer` (this package's exact 1-D k-means) + RF.

Run a benchmark suite (sweeps `n_bins` and a small RF hyper-parameter grid,
uses repeated K-fold CV so all variants share identical folds):

```bash
uv run python benchmarks/randomforest_discretization_benchmark.py --repeats 3
```

This appends runs to `.benchmarks/randomforest_discretization_runs.jsonl`.
Additional flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--repeats N` | `3` | Number of CV repeats per config. |
| `--datasets ...` | all | Subset of datasets (e.g. `breast_cancer synth_clf`). |
| `--n-bins ...` | `2 4 8 16 32 64` | Bin counts to sweep. |
| `--variants ...` | all four | Variants to include. |
| `--seed N` | `42` | Base random seed. |
| `--output PATH` | `.benchmarks/randomforest_discretization_runs.jsonl` | Output JSONL file. |

Generate textual summaries and optional HTML reports:

```bash
uv run python benchmarks/randomforest_discretization_compare.py
uv run python benchmarks/randomforest_discretization_compare.py --plots
```

With `--plots`, three interactive HTML reports are written to `.benchmarks/reports/`:

- `rf_quality_vs_bins.html`       — quality metric vs. n_bins, one line per variant/dataset.
- `rf_speed_vs_bins.html`         — chosen speed metric vs. n_bins per variant.
- `rf_speed_quality_pareto.html`  — scatter with the Pareto frontier marked (★ = Pareto-optimal).

The textual output enumerates Pareto-optimal configs per dataset and addresses three
headline comparisons per dataset: `optimal` vs. `kmeans` quality/speed at equal bins;
`optimal`/`kmeans` vs. `quantile`; and whether any discretized variant beats `none` (a
regularisation-effect signal).

Use `--speed-metric` to change the speed axis for Pareto and speed plots
(choices: `total_time`, `rf_fit_time`, `disc_fit_time`, `disc_transform_time`, `rf_predict_time`).

If `plotly` is unavailable, the compare command still prints all textual summaries.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_bins`       | `5`     | Number of clusters / bins per feature column. If `None`, search over `n_bins_range`. |
| `n_bins_range` | `None`  | Inclusive `(n_bins_min, n_bins_max)` search interval used when `n_bins=None`. Defaults to `(1, n_samples)` at fit time. |
| `scorer`       | `None`  | Callable used when `n_bins=None` to score each candidate clustering (higher is better). |

## Attributes (after `fit`)

| Attribute      | Shape              | Description |
|----------------|--------------------|-------------|
| `centroids_`   | list of (n_bins_j,)  | Centroid of each bin per feature |
| `bin_edges_`   | list of (n_bins_j+1,)| Threshold edges (includes ±∞ sentinels) |
| `n_bins_`      | list of int          | Selected number of bins per feature |
| `n_features_in_` | int              | Number of features seen at fit time |
