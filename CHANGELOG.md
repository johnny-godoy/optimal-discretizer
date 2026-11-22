# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- scriv-insert-here -->

<a id='changelog-0.1.0'></a>
## [0.1.0] - 2026-11-22

### Added

- First release on PyPI: `optimal-discretizer`, with wheels for CPython 3.11 to 3.15 (and the free-threaded 3.14t and 3.15t) on Linux (x86_64 and aarch64, glibc and musl), macOS (arm64 and x86_64) and Windows (AMD64).
- `OptimalDiscretizer`, a scikit-learn transformer that bins each feature with exact 1-D k-means: the bins of each feature have the smallest sum of squared distances to their centroids.
- `kmeans_1d`, exact k-means of one array of values, with a Cython kernel that follows the dynamic program of Grønlund et al. (2017) and finds each layer with SMAWK.
- A Lean 4 proof, with a paper on the documentation site, that the kernel returns a global minimum of the k-means objective in exact arithmetic.
- Scorers that choose the number of bins of each feature when `n_bins=None`: `"mdl_bits_knee"`, `"kneed_inertia"`, `"mdl_gaussian"` and `"second_difference"`, and `MaxScore` for a custom score. They are heuristics.
- `BinCountWarning` when a feature has fewer distinct values than the number of bins; the feature then gets one bin for each distinct value.
