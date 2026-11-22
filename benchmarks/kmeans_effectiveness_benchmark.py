"""Benchmark k-means effectiveness against brute-force optimal and Lloyd's algorithm."""

from __future__ import annotations

import datetime as dt
import itertools
import math
import statistics
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from time import perf_counter

import attrs
import cyclopts
import numpy as np
import numpy.typing as npt
from sklearn.cluster import KMeans

from benchmarks.run_files import append_jsonl, dumps, resolve_git_commit
from optimal_discretizer import kmeans_1d

DEFAULT_REPEATS = 8
DEFAULT_OUTPUT = Path(".benchmarks/kmeans_effectiveness_runs.jsonl")
NUMERIC_EPSILON = 1e-12

SerializedProblemResults = dict[str, dict[str, dict[str, float]]]


@attrs.define
class BenchmarkProblem:
    """Single benchmark problem definition."""

    name: str
    n_samples: int
    n_clusters: int
    datasets: list[npt.NDArray[np.float64]]


@attrs.define
class AlgorithmResult:
    """Collected benchmark metrics for one algorithm in one problem."""

    optimality_pct: float
    mean_gap_pct: float
    mean_ms: float
    median_ms: float


def segment_cost(prefix: npt.NDArray[np.float64], prefix_sq: npt.NDArray[np.float64], start: int, end: int) -> float:
    """Return within-segment SSE for sorted values in half-open range [start, end).

    Parameters
    ----------
    prefix : ndarray of shape (n_samples + 1,)
        prefix[i] is the sum of the first i sorted values, with prefix[0] = 0.0.
    prefix_sq : ndarray of shape (n_samples + 1,)
        prefix_sq[i] is the sum of squares of the first i sorted values, with prefix_sq[0] = 0.0.
    start : int
        Starting index of the segment (inclusive).
    end : int
        Ending index of the segment (exclusive).

    Returns
    -------
    float
        The sum of squared deviations from the mean for the segment defined by [start, end).

    """
    count = end - start
    if count <= 0:
        return 0.0
    total = prefix[end] - prefix[start]
    total_sq = prefix_sq[end] - prefix_sq[start]
    mean = total / float(count)
    return float(total_sq - (2.0 * mean * total) + (count * mean * mean))


def brute_force_optimal_cost(values: npt.NDArray[np.float64], n_clusters: int) -> float:
    """Return exact global optimum SSE by exhaustively enumerating sorted partitions.

    Parameters
    ----------
    values : ndarray of shape (n_samples,)
        Input values to cluster.
    n_clusters : int
        Number of clusters to partition the values into.

    Returns
    -------
    float
        The minimum possible sum of squared deviations from cluster means achievable by any partition.

    Raises
    ------
    ValueError
        If n_clusters is not in the range [1, n_samples].

    """
    sorted_values = np.sort(values)
    n_samples = int(sorted_values.shape[0])
    if n_clusters < 1 or n_clusters > n_samples:
        msg = (
            f"n_clusters must satisfy 1 <= n_clusters <= n_samples, got n_clusters={n_clusters}, n_samples={n_samples}"
        )
        raise ValueError(msg)

    prefix = np.empty(n_samples + 1, dtype=np.float64)
    prefix_sq = np.empty(n_samples + 1, dtype=np.float64)
    prefix[0] = 0.0
    prefix_sq[0] = 0.0
    prefix[1:] = np.cumsum(sorted_values, dtype=np.float64)
    prefix_sq[1:] = np.cumsum(sorted_values * sorted_values, dtype=np.float64)

    if n_clusters == 1:
        return segment_cost(prefix, prefix_sq, 0, n_samples)

    best_cost = math.inf
    cut_positions = range(1, n_samples)
    for cuts in itertools.combinations(cut_positions, n_clusters - 1):
        start = 0
        current_cost = 0.0
        for stop in (*cuts, n_samples):
            current_cost += segment_cost(prefix, prefix_sq, start, stop)
            if current_cost >= best_cost:
                break
            start = stop
        best_cost = min(best_cost, current_cost)

    return float(best_cost)


def main_algorithm_cost(values: npt.NDArray[np.float64], n_clusters: int) -> float:
    """Run repository main algorithm and return SSE.

    Parameters
    ----------
    values : ndarray of shape (n_samples,)
        Input values to cluster.
    n_clusters : int
        Number of clusters to partition the values into.

    Returns
    -------
    float
        The sum of squared deviations from cluster means for the partition produced by the main algorithm.

    """
    return kmeans_1d(values, n_clusters).inertia


def lloyd_algorithm_cost(values: npt.NDArray[np.float64], n_clusters: int, seed: int) -> float:
    """Run sklearn KMeans with Lloyd iterations and return inertia.

    Parameters
    ----------
    values : ndarray of shape (n_samples,)
        Input values to cluster.
    n_clusters : int
        Number of clusters to partition the values into.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    float
        The sum of squared deviations from cluster means for the partition produced by the Lloyd algorithm.

    """
    estimator = KMeans(
        n_clusters=n_clusters,
        n_init=10,
        algorithm="lloyd",
        random_state=seed,
    )
    estimator.fit(values.reshape(-1, 1))
    return float(estimator.inertia_)


@attrs.frozen(kw_only=True)
class ProblemSpec:
    """The settings of one synthetic benchmark problem.

    Attributes
    ----------
    name : str
        Unique name for the problem.
    n_samples : int
        Number of samples in each trial dataset.
    n_clusters : int
        Number of clusters to generate in each trial dataset.
    trial_count : int
        Number of independent trial datasets to generate for the problem.
    seed : int
        Random seed for reproducibility.
    separation : float
        Average distance between cluster centers.
    noise_scale : float
        Standard deviation of Gaussian noise added to cluster samples.
    outlier_rate : float
        Proportion of samples to designate as outliers and shift by a large random amount.

    """

    name: str
    n_samples: int
    n_clusters: int
    trial_count: int
    seed: int
    separation: float
    noise_scale: float
    outlier_rate: float


def create_problem(spec: ProblemSpec) -> BenchmarkProblem:
    """Create one deterministic synthetic benchmark problem.

    Parameters
    ----------
    spec : ProblemSpec
        The settings of the problem.

    Returns
    -------
    BenchmarkProblem
        The generated benchmark problem with the given settings.

    """
    rng = np.random.default_rng(spec.seed)
    datasets: list[npt.NDArray[np.float64]] = []

    base_centers = np.linspace(-spec.separation, spec.separation, num=spec.n_clusters, dtype=np.float64)
    for _ in range(spec.trial_count):
        source_centers = rng.choice(base_centers, size=spec.n_samples, replace=True)
        values = rng.normal(loc=source_centers, scale=spec.noise_scale).astype(np.float64)

        outlier_count = round(spec.n_samples * spec.outlier_rate)
        if outlier_count > 0:
            outlier_indices = rng.choice(spec.n_samples, size=outlier_count, replace=False)
            outlier_shifts = rng.normal(loc=0.0, scale=spec.separation * 1.4, size=outlier_count)
            values[outlier_indices] += outlier_shifts

        datasets.append(values)

    return BenchmarkProblem(
        name=spec.name,
        n_samples=spec.n_samples,
        n_clusters=spec.n_clusters,
        datasets=datasets,
    )


def create_problems() -> list[BenchmarkProblem]:
    """Build benchmark problems with varied cluster geometry.

    Returns
    -------
    list of BenchmarkProblem
        The problems of the suite.

    """
    specs = [
        ProblemSpec(
            name="small-separated",
            n_samples=14,
            n_clusters=3,
            trial_count=80,
            seed=11,
            separation=5.0,
            noise_scale=0.35,
            outlier_rate=0.00,
        ),
        ProblemSpec(
            name="medium-overlap",
            n_samples=16,
            n_clusters=4,
            trial_count=70,
            seed=23,
            separation=3.2,
            noise_scale=0.95,
            outlier_rate=0.03,
        ),
        ProblemSpec(
            name="skewed-outliers",
            n_samples=18,
            n_clusters=3,
            trial_count=60,
            seed=37,
            separation=4.0,
            noise_scale=0.75,
            outlier_rate=0.10,
        ),
        ProblemSpec(
            name="heavy-overlap",
            n_samples=20,
            n_clusters=4,
            trial_count=55,
            seed=47,
            separation=2.4,
            noise_scale=1.20,
            outlier_rate=0.05,
        ),
    ]
    return [create_problem(spec) for spec in specs]


def _main_cost(values: npt.NDArray[np.float64], n_clusters: int, seed: int) -> float:
    """Return the cost of the main algorithm. It is deterministic, so it ignores the seed.

    Returns
    -------
    float
        The sum of squared deviations from the cluster means.

    """
    del seed
    return main_algorithm_cost(values, n_clusters)


def _brute_force_cost(values: npt.NDArray[np.float64], n_clusters: int, seed: int) -> float:
    """Return the cost of the search over every partition. It is deterministic, so it ignores the seed.

    Returns
    -------
    float
        The smallest sum of squared deviations from the cluster means.

    """
    del seed
    return brute_force_optimal_cost(values, n_clusters)


ALGORITHMS: Mapping[str, Callable[[npt.NDArray[np.float64], int, int], float]] = {
    "main": _main_cost,
    "lloyd": lambda values, n_clusters, seed: lloyd_algorithm_cost(values, n_clusters, seed=seed),
    "bruteforce": _brute_force_cost,
}
"""The algorithms of the benchmark, by name. Each takes the values, the number of clusters and a seed."""


def cost_for_algorithm(
    algorithm_name: str,
    values: npt.NDArray[np.float64],
    n_clusters: int,
    seed: int,
) -> float:
    """Compute the sum of squared deviations of one algorithm on one dataset.

    Returns
    -------
    float
        The cost of the partition that the algorithm returns.

    Raises
    ------
    ValueError
        If the algorithm is not in ``ALGORITHMS``.

    """
    if algorithm_name not in ALGORITHMS:
        msg = f"Unknown algorithm {algorithm_name!r}."
        raise ValueError(msg)
    return ALGORITHMS[algorithm_name](values, n_clusters, seed)


def run_timed_predictions(
    algorithm_name: str,
    problem: BenchmarkProblem,
    repeats: int,
) -> list[float]:
    """Measure the time of each trial in milliseconds.

    Returns
    -------
    list of float
        One duration for each repeat and each trial.

    """
    durations_ms: list[float] = []

    for repeat_index in range(repeats):
        for trial_index, values in enumerate(problem.datasets):
            start = perf_counter()
            cost_for_algorithm(algorithm_name, values, problem.n_clusters, seed=repeat_index * 1_000_000 + trial_index)
            end = perf_counter()
            durations_ms.append((end - start) * 1000.0)

    return durations_ms


def evaluate_algorithm(
    algorithm_name: str,
    problem: BenchmarkProblem,
    repeats: int,
) -> AlgorithmResult:
    """Evaluate one algorithm on one problem.

    Returns
    -------
    AlgorithmResult
        The share of optimal results, the mean gap and the run times.

    """
    optimal_matches = 0
    gap_values_pct: list[float] = []

    for trial_index, values in enumerate(problem.datasets):
        optimal_cost = brute_force_optimal_cost(values, problem.n_clusters)
        algorithm_cost = cost_for_algorithm(
            algorithm_name=algorithm_name,
            values=values,
            n_clusters=problem.n_clusters,
            seed=trial_index,
        )
        if math.isclose(algorithm_cost, optimal_cost, rel_tol=0.0, abs_tol=1e-9):
            optimal_matches += 1
        denominator = max(optimal_cost, NUMERIC_EPSILON)
        gap_pct = max((algorithm_cost - optimal_cost) / denominator, 0.0) * 100.0
        gap_values_pct.append(gap_pct)

    durations_ms = run_timed_predictions(
        algorithm_name=algorithm_name,
        problem=problem,
        repeats=repeats,
    )

    return AlgorithmResult(
        optimality_pct=(optimal_matches / len(problem.datasets)) * 100.0,
        mean_gap_pct=statistics.fmean(gap_values_pct),
        mean_ms=statistics.fmean(durations_ms),
        median_ms=statistics.median(durations_ms),
    )


def run_suite(repeats: int) -> dict[str, dict[str, AlgorithmResult]]:
    """Run every algorithm on every problem.

    Returns
    -------
    dict
        The result of each algorithm, by problem and algorithm name.

    """
    suite_results: dict[str, dict[str, AlgorithmResult]] = {}

    for problem in create_problems():
        problem_results = {
            "main": evaluate_algorithm(algorithm_name="main", problem=problem, repeats=repeats),
            "lloyd": evaluate_algorithm(algorithm_name="lloyd", problem=problem, repeats=repeats),
            "bruteforce": evaluate_algorithm(algorithm_name="bruteforce", problem=problem, repeats=repeats),
        }
        suite_results[problem.name] = problem_results

    return suite_results


def serialize_results(
    suite_results: dict[str, dict[str, AlgorithmResult]],
) -> SerializedProblemResults:
    """Convert the results to a structure that orjson writes.

    Returns
    -------
    dict
        The metrics of each algorithm, by problem and algorithm name.

    """
    serialized: SerializedProblemResults = {}
    for problem_name, algorithms in suite_results.items():
        serialized[problem_name] = {
            algorithm_name: {
                "optimality_pct": metrics.optimality_pct,
                "mean_gap_pct": metrics.mean_gap_pct,
                "mean_ms": metrics.mean_ms,
                "median_ms": metrics.median_ms,
            }
            for algorithm_name, metrics in algorithms.items()
        }
    return serialized


def print_summary(suite_results: dict[str, dict[str, AlgorithmResult]]) -> None:
    """Print benchmark results in a compact table-like format."""
    header = (
        "problem",
        "algorithm",
        "optimality_pct",
        "mean_gap_pct",
        "mean_ms",
        "median_ms",
    )
    lines = ["\t".join(header)]

    for problem_name, algorithms in suite_results.items():
        for algorithm_name, metrics in algorithms.items():
            row = (
                problem_name,
                algorithm_name,
                f"{metrics.optimality_pct:.2f}",
                f"{metrics.mean_gap_pct:.4f}",
                f"{metrics.mean_ms:.4f}",
                f"{metrics.median_ms:.4f}",
            )
            lines.append("\t".join(row))

    sys.stdout.write("\n".join(lines))
    sys.stdout.write("\n")


app: cyclopts.App = cyclopts.App(
    name="kmeans_effectiveness_benchmark",
    help=__doc__.splitlines()[0] if __doc__ else None,
    result_action="return_value",
)


@app.default
def main(*, repeats: int = DEFAULT_REPEATS, output: Path = DEFAULT_OUTPUT) -> int:
    """Run the benchmark suite and append the run to a JSONL file.

    Parameters
    ----------
    repeats : int
        How many timing rounds to run for each trial of each problem.
    output : Path
        The JSONL file that the run is appended to.

    Returns
    -------
    int
        0 when the run is saved.

    """
    repo_root = Path(__file__).resolve().parent.parent
    suite_results = run_suite(repeats=repeats)

    run_payload = {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "commit": resolve_git_commit(repo_root),
        "repeats": repeats,
        "problems": serialize_results(suite_results),
    }

    append_jsonl(output, dumps(run_payload))
    print_summary(suite_results)
    sys.stdout.write(f"\nSaved run to {output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(app())
