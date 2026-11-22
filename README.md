# optimal-discretizer

<!-- --8<-- [start:intro] -->
[![CI](https://github.com/johnny-godoy/optimal-discretizer/actions/workflows/ci.yml/badge.svg)](https://github.com/johnny-godoy/optimal-discretizer/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/optimal-discretizer)](https://pypi.org/project/optimal-discretizer/)
[![Python](https://img.shields.io/pypi/pyversions/optimal-discretizer)](https://pypi.org/project/optimal-discretizer/)

`optimal-discretizer` bins each feature of a data set with exact one-dimensional k-means. For each feature it finds
the clustering into `n_bins` clusters with the smallest sum of squared distances to the cluster means: a global
minimum, not the local minimum that Lloyd's algorithm finds. The bins are the intervals between the midpoints of
consecutive centroids. `OptimalDiscretizer` is a scikit-learn transformer, so it works in a `Pipeline`.

The kernel is Cython. It follows the dynamic program of
[Grønlund et al. (2017)](https://arxiv.org/abs/1701.07204) and finds the minimum of each layer with the SMAWK
algorithm. It clusters one million values into ten clusters in about a second on a laptop.

A Lean 4 proof checks that the kernel returns a global minimum of the k-means objective, in exact arithmetic. The
[proof page](https://johnny-godoy.github.io/optimal-discretizer/kmeans-1d-proof/) states what the proof covers and
what it does not cover, such as floating point.
<!-- --8<-- [end:intro] -->

## Install

<!-- --8<-- [start:install] -->
```bash
pip install optimal-discretizer
```

The wheels support CPython 3.11 to 3.15 on Linux (x86_64 and aarch64, glibc and musl), macOS (arm64 and x86_64) and
Windows (AMD64). On other platforms, pip builds the package from the source distribution, which needs a C compiler.
<!-- --8<-- [end:install] -->

## Quick start

<!-- --8<-- [start:quickstart] -->
```python
import numpy as np
from optimal_discretizer import OptimalDiscretizer

random_generator = np.random.default_rng(0)
features = random_generator.normal(size=(200, 3))

discretizer = OptimalDiscretizer(n_bins=5)
bins = discretizer.fit_transform(features)  # shape (200, 3), values 0.0 to 4.0

print(discretizer.centroids_[0].round(2))  # the centroid of each bin of the first feature
print(discretizer.bin_edges_[0].round(2))  # the bin edges, with -inf and +inf at the ends
```

`OptimalDiscretizer` works in a scikit-learn `Pipeline`:

```python
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

target = (features[:, 0] + features[:, 1] > 0).astype(int)
pipeline = Pipeline([("bins", OptimalDiscretizer(n_bins=10)), ("model", LogisticRegression())])
pipeline.fit(features, target)
```

`kmeans_1d` clusters one array of values:

```python
from optimal_discretizer import kmeans_1d

clustering = kmeans_1d([1.0, 10.0, 2.0, 11.0, 30.0], n_clusters=3)
print(clustering.labels)  # [0 1 0 1 2]
print(clustering.centroids)  # [ 1.5 10.5 30. ]
```
<!-- --8<-- [end:quickstart] -->

## Choose the number of bins

<!-- --8<-- [start:scorers] -->
With `n_bins=None`, a scorer chooses the number of bins of each feature from the exact clusterings for each number in
`n_bins_range`. The scorers are heuristics: each clustering is exact, but the chosen number of bins is not optimal in
any proved sense.

| Scorer | How it chooses |
| --- | --- |
| `"mdl_bits_knee"` | The knee of the curve of data bits against model bits of a two-part minimum description length code. The Kneedle algorithm of `kneed` finds the knee. |
| `"kneed_inertia"` | The knee of the curve of inertia against the number of bins, with the Kneedle algorithm. |
| `"mdl_gaussian"` | The shortest two-part code length, with a Gaussian code for the residuals of each bin. |
| `"second_difference"` | The largest second difference of the inertia curve: the elbow. |

```python
discretizer = OptimalDiscretizer(n_bins=None, n_bins_range=(1, 8), scorer="mdl_bits_knee")
discretizer.fit(features)
print(discretizer.n_bins_)  # the number of bins of each feature
```

A scorer can also be an object with a `select(values, candidates)` method, for example `MaxScore(score_function)`.
<!-- --8<-- [end:scorers] -->

## Parameters and attributes

<!-- --8<-- [start:parameters] -->
| Parameter | Default | Description |
| --- | --- | --- |
| `n_bins` | `5` | The number of bins of each feature. `None` lets `scorer` choose it. |
| `n_bins_range` | `None` | The smallest and the largest number of bins that `scorer` can choose. `None` is `(1, distinct values)`. |
| `scorer` | `None` | A name from the table above, or an object with a `select` method. Needed when `n_bins` is `None`. |

| Attribute | Description |
| --- | --- |
| `centroids_` | The centroids of the bins of each feature, in increasing order. |
| `bin_edges_` | The bin edges of each feature, with `-inf` and `+inf` at the ends. |
| `n_bins_` | The number of bins of each feature. |
| `inertia_` | The sum of squared distances of the training values of each feature to their centroids. |

If a feature has fewer distinct values than `n_bins`, the feature gets one bin for each distinct value, and `fit` warns
with `BinCountWarning`. NaN and infinite values raise `ValueError`.
<!-- --8<-- [end:parameters] -->

## Benchmarks

<!-- --8<-- [start:benchmarks] -->
The repository holds two benchmarks. Run them from a clone, with `uv run`.

- `python -m benchmarks.kmeans_effectiveness_benchmark` compares the cost of `kmeans_1d` with Lloyd's algorithm
  (`sklearn.cluster.KMeans`) and with a search over every partition, and
  `python -m benchmarks.kmeans_effectiveness_compare` summarizes the runs.
- `python -m benchmarks.randomforest_discretization_benchmark` measures the quality and the speed of a random forest
  after quantile, k-means and exact binning, and `python -m benchmarks.randomforest_discretization_compare` prints the
  Pareto front of speed and quality. `--plots` writes HTML plots if `plotly` is installed.

Each command takes `--help`. The runs go to JSONL files in `.benchmarks/`.
<!-- --8<-- [end:benchmarks] -->

## Development

<!-- --8<-- [start:development] -->
Install [uv](https://docs.astral.sh/uv/), [just](https://just.systems/) and a C compiler. Then run `just sync` to
install the environment and the git hooks. The environment holds an editable install: when you import the package,
meson-python compiles the Cython kernel again if its source changed. `just` lists every recipe.

| Recipe | What it does |
| --- | --- |
| `just check` | Runs every prek hook on every file. |
| `just clones` | Fails on a copy-paste clone that `origin/main` lacks. |
| `just test` | Runs the unit tests with the 100% branch coverage gate. |
| `just test-docs` | Runs the code examples of the docs and the docstrings. |
| `just test-one <test>` | Runs one test without the coverage gate. |
| `just mutate` | Runs mutation testing on the lines that changed since `origin/main`. |
| `just docs` | Builds the docs as CI does. |
| `just changelog` | Adds a changelog fragment. |
| `just proofs` | Checks the Lean proofs. |

[`CONTRIBUTING.md`](https://github.com/johnny-godoy/optimal-discretizer/blob/main/CONTRIBUTING.md) has the rules for
changes, commits and pull requests.
<!-- --8<-- [end:development] -->

## Release

<!-- --8<-- [start:release] -->
After each green CI run on `main`, the release workflow gives the changelog fragments a version, tags it, builds the
wheels with cibuildwheel and the source distribution, checks them, and creates the GitHub release with checksums and
an SBOM. It uploads the files to PyPI with trusted publishing only if the repository variable `PUBLISH_TO_PYPI` is
`true`. Do these steps once:

1. On PyPI, add a pending trusted publisher for `johnny-godoy/optimal-discretizer`, the workflow `release.yml` and the
   environment `pypi`.
2. On GitHub, create the environment `pypi` with a required reviewer.
3. Set the repository variable `PUBLISH_TO_PYPI` to `true` when the first release is ready.
<!-- --8<-- [end:release] -->

## License

MIT. See [`LICENSE`](https://github.com/johnny-godoy/optimal-discretizer/blob/main/LICENSE).
