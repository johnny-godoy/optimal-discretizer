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
