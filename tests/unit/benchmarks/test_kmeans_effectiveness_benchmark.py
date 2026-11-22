"""Tests of the benchmark of k-means effectiveness."""

from pathlib import Path

import numpy as np
import orjson
import pytest
from benchmarks import kmeans_effectiveness_benchmark as benchmark


def test_the_main_algorithm_matches_the_search_over_every_partition() -> None:
    values = np.random.default_rng(0).normal(size=12)
    assert benchmark.main_algorithm_cost(values, 3) == pytest.approx(benchmark.brute_force_optimal_cost(values, 3))


def test_lloyd_never_beats_the_optimum() -> None:
    values = np.random.default_rng(1).normal(size=14)
    assert benchmark.lloyd_algorithm_cost(values, 3, seed=0) >= benchmark.brute_force_optimal_cost(values, 3) - 1e-9


def test_the_search_rejects_a_bad_cluster_count() -> None:
    with pytest.raises(ValueError, match="n_clusters must satisfy"):
        benchmark.brute_force_optimal_cost(np.array([1.0, 2.0]), 3)


def test_an_unknown_algorithm_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown algorithm 'elbow'"):
        benchmark.cost_for_algorithm("elbow", np.array([1.0, 2.0]), 1, seed=0)


def test_each_problem_has_its_trials() -> None:
    problems = benchmark.create_problems()
    assert all(len(problem.datasets) > 0 for problem in problems)
    assert len({problem.name for problem in problems}) == len(problems)


def test_main_appends_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    small = benchmark.ProblemSpec(
        name="tiny",
        n_samples=6,
        n_clusters=2,
        trial_count=2,
        seed=0,
        separation=3.0,
        noise_scale=0.1,
        outlier_rate=0.0,
    )
    monkeypatch.setattr(benchmark, "create_problems", lambda: [benchmark.create_problem(small)])
    output = tmp_path / "runs.jsonl"
    assert benchmark.app(["--repeats", "1", "--output", str(output)]) == 0
    run = orjson.loads(output.read_bytes())
    assert run["problems"]["tiny"]["main"]["optimality_pct"] == pytest.approx(100.0)
    assert set(run["problems"]["tiny"]) == {"main", "lloyd", "bruteforce"}
