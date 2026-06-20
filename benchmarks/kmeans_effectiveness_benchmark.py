"""Benchmark k-means effectiveness against brute-force optimal and Lloyd's algorithm."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import itertools
import json
import math
import statistics
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import numpy.typing as npt
from sklearn.cluster import KMeans

try:
    from src.transformer import OptimalDiscretizer
except ModuleNotFoundError as error:
    if error.name != "src._core":
        raise

    import pyximport

    pyximport.install(setup_args={"include_dirs": np.get_include()}, language_level=3)
    from src.transformer import OptimalDiscretizer

DEFAULT_REPEATS = 8
DEFAULT_OUTPUT = Path(".benchmarks/kmeans_effectiveness_runs.jsonl")
NUMERIC_EPSILON = 1e-12

SerializedProblemResults = dict[str, dict[str, dict[str, float]]]


@dataclasses.dataclass(slots=True)
class BenchmarkProblem:
    """Single benchmark problem definition."""

    name: str
    n_samples: int
    n_clusters: int
    datasets: list[npt.NDArray[np.float64]]


@dataclasses.dataclass(slots=True)
class AlgorithmResult:
    """Collected benchmark metrics for one algorithm in one problem."""

    optimality_pct: float
    mean_gap_pct: float
    mean_ms: float
    median_ms: float


def segment_cost(prefix: npt.NDArray[np.float64], prefix_sq: npt.NDArray[np.float64], start: int, end: int) -> float:
    """Return within-segment SSE for sorted values in half-open range [start, end)."""
    count = end - start
    if count <= 0:
        return 0.0
    total = prefix[end] - prefix[start]
    total_sq = prefix_sq[end] - prefix_sq[start]
    mean = total / float(count)
    return float(total_sq - (2.0 * mean * total) + (count * mean * mean))


def brute_force_optimal_cost(values: npt.NDArray[np.float64], n_clusters: int) -> float:
    """Return exact global optimum SSE by exhaustively enumerating sorted partitions."""
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
    """Run repository main algorithm and return SSE."""
    discretizer = OptimalDiscretizer(n_bins=n_clusters)
    labels = discretizer.fit_transform(values.reshape(-1, 1)).ravel().astype(np.int64)
    centroids = discretizer.centroids_[0]
    reconstructed = centroids[labels]
    residuals = values - reconstructed
    return float(np.dot(residuals, residuals))


def lloyd_algorithm_cost(values: npt.NDArray[np.float64], n_clusters: int, seed: int) -> float:
    """Run sklearn KMeans with Lloyd iterations and return inertia."""
    estimator = KMeans(
        n_clusters=n_clusters,
        n_init=10,
        algorithm="lloyd",
        random_state=seed,
    )
    estimator.fit(values.reshape(-1, 1))
    return float(estimator.inertia_)


def create_problem(
    name: str,
    n_samples: int,
    n_clusters: int,
    trial_count: int,
    seed: int,
    separation: float,
    noise_scale: float,
    outlier_rate: float,
) -> BenchmarkProblem:
    """Create one deterministic synthetic benchmark problem."""
    rng = np.random.default_rng(seed)
    datasets: list[npt.NDArray[np.float64]] = []

    base_centers = np.linspace(-separation, separation, num=n_clusters, dtype=np.float64)
    for _ in range(trial_count):
        source_centers = rng.choice(base_centers, size=n_samples, replace=True)
        values = rng.normal(loc=source_centers, scale=noise_scale).astype(np.float64)

        outlier_count = round(n_samples * outlier_rate)
        if outlier_count > 0:
            outlier_indices = rng.choice(n_samples, size=outlier_count, replace=False)
            outlier_shifts = rng.normal(loc=0.0, scale=separation * 1.4, size=outlier_count)
            values[outlier_indices] += outlier_shifts

        datasets.append(values)

    return BenchmarkProblem(
        name=name,
        n_samples=n_samples,
        n_clusters=n_clusters,
        datasets=datasets,
    )


def create_problems() -> list[BenchmarkProblem]:
    """Build benchmark problems with varied cluster geometry."""
    return [
        create_problem(
            name="small-separated",
            n_samples=14,
            n_clusters=3,
            trial_count=80,
            seed=11,
            separation=5.0,
            noise_scale=0.35,
            outlier_rate=0.00,
        ),
        create_problem(
            name="medium-overlap",
            n_samples=16,
            n_clusters=4,
            trial_count=70,
            seed=23,
            separation=3.2,
            noise_scale=0.95,
            outlier_rate=0.03,
        ),
        create_problem(
            name="skewed-outliers",
            n_samples=18,
            n_clusters=3,
            trial_count=60,
            seed=37,
            separation=4.0,
            noise_scale=0.75,
            outlier_rate=0.10,
        ),
        create_problem(
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


def run_timed_predictions(
    algorithm_name: str,
    problem: BenchmarkProblem,
    repeats: int,
) -> list[float]:
    """Measure per-trial prediction time in milliseconds."""
    durations_ms: list[float] = []

    for repeat_index in range(repeats):
        for trial_index, values in enumerate(problem.datasets):
            start = perf_counter()
            if algorithm_name == "main":
                main_algorithm_cost(values, problem.n_clusters)
            elif algorithm_name == "lloyd":
                seed = repeat_index * 1_000_000 + trial_index
                lloyd_algorithm_cost(values, problem.n_clusters, seed=seed)
            elif algorithm_name == "bruteforce":
                brute_force_optimal_cost(values, problem.n_clusters)
            else:
                msg = f"Unknown algorithm {algorithm_name!r}."
                raise ValueError(msg)
            end = perf_counter()
            durations_ms.append((end - start) * 1000.0)

    return durations_ms


def cost_for_algorithm(
    algorithm_name: str,
    values: npt.NDArray[np.float64],
    n_clusters: int,
    seed: int,
) -> float:
    """Dispatch and compute SSE for one algorithm."""
    if algorithm_name == "main":
        return main_algorithm_cost(values, n_clusters)
    if algorithm_name == "lloyd":
        return lloyd_algorithm_cost(values, n_clusters, seed=seed)
    if algorithm_name == "bruteforce":
        return brute_force_optimal_cost(values, n_clusters)

    msg = f"Unknown algorithm {algorithm_name!r}."
    raise ValueError(msg)


def evaluate_algorithm(
    algorithm_name: str,
    problem: BenchmarkProblem,
    repeats: int,
) -> AlgorithmResult:
    """Evaluate one algorithm and return quality and runtime metrics."""
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


def resolve_git_commit(repo_root: Path) -> str:
    """Resolve current git commit hash without shelling out."""
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


def run_suite(repeats: int) -> dict[str, dict[str, AlgorithmResult]]:
    """Run benchmark suite and return per-problem algorithm results."""
    suite_results: dict[str, dict[str, AlgorithmResult]] = {}

    for problem in create_problems():
        problem_results = {
            "main": evaluate_algorithm(algorithm_name="main", problem=problem, repeats=repeats),
            "lloyd": evaluate_algorithm(algorithm_name="lloyd", problem=problem, repeats=repeats),
            "bruteforce": evaluate_algorithm(algorithm_name="bruteforce", problem=problem, repeats=repeats),
        }
        suite_results[problem.name] = problem_results

    return suite_results


def append_run(
    run_output_path: Path,
    run_payload: dict[str, str | int | SerializedProblemResults],
) -> None:
    """Append run payload to JSONL file."""
    run_output_path.parent.mkdir(parents=True, exist_ok=True)
    with run_output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run_payload))
        handle.write("\n")


def serialize_results(
    suite_results: dict[str, dict[str, AlgorithmResult]],
) -> SerializedProblemResults:
    """Convert dataclass results to a JSON-serializable structure."""
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


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for benchmark execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help="How many timing rounds to execute for each problem trial.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSONL file where benchmark runs are appended.",
    )
    return parser.parse_args()


def main() -> None:
    """Execute benchmark suite and persist run results."""
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    suite_results = run_suite(repeats=args.repeats)

    run_payload = {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "commit": resolve_git_commit(repo_root),
        "repeats": args.repeats,
        "problems": serialize_results(suite_results),
    }

    append_run(run_output_path=args.output, run_payload=run_payload)
    print_summary(suite_results)
    sys.stdout.write(f"\nSaved run to {args.output}\n")


if __name__ == "__main__":
    main()
