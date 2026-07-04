"""Smoke tests for the RandomForest discretization benchmark suite."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest
from benchmarks.randomforest_discretization_benchmark import (
    DATASET_REGISTRY,
    load_single_dataset,
)
from benchmarks.randomforest_discretization_benchmark import (
    main as benchmark_main,
)
from benchmarks.randomforest_discretization_compare import (
    load_runs,
    pareto_front,
    print_summary,
)

if TYPE_CHECKING:
    from pathlib import Path


def _run_minimal_benchmark(output_path: Path) -> None:
    """Execute one config and write a JSONL row to output_path."""
    sys.argv = [
        "randomforest_discretization_benchmark.py",
        "--repeats", "1",
        "--datasets", "synth_clf",
        "--n-bins", "2",
        "--variants", "none", "quantile", "optimal",
        "--output", str(output_path),
    ]
    benchmark_main()


def _write_minimal_jsonl(path: Path) -> None:
    """Write a hand-crafted minimal JSONL record for compare script testing."""
    record = {
        "timestamp_utc": "2024-01-01T00:00:00+00:00",
        "commit": "abc1234",
        "repeats": 1,
        "cv_folds": 5,
        "cv_repeats": 1,
        "seed": 42,
        "n_bins_sweep": [2, 4],
        "n_estimators_grid": [100],
        "max_depth_grid": [None],
        "n_jobs": 1,
        "timing_method": "test",
        "platform": "test",
        "python_version": "3.12",
        "sklearn_version": "1.5",
        "numpy_version": "2.0",
        "package_version": "0.1.0",
        "results": {
            "breast_cancer": [
                {
                    "dataset": "breast_cancer",
                    "task": "classification",
                    "variant": "none",
                    "n_bins": None,
                    "n_estimators": 100,
                    "max_depth": None,
                    "seed": 42,
                    "roc_auc_mean": 0.98,
                    "roc_auc_std": 0.01,
                    "accuracy_mean": 0.96,
                    "accuracy_std": 0.01,
                    "macro_f1_mean": 0.95,
                    "macro_f1_std": 0.01,
                    "disc_fit_time_mean": 0.0,
                    "disc_fit_time_std": 0.0,
                    "disc_transform_time_mean": 0.0,
                    "disc_transform_time_std": 0.0,
                    "rf_fit_time_mean": 0.5,
                    "rf_fit_time_std": 0.05,
                    "rf_predict_time_mean": 0.01,
                    "rf_predict_time_std": 0.001,
                    "total_time_mean": 0.51,
                    "total_time_std": 0.05,
                },
                {
                    "dataset": "breast_cancer",
                    "task": "classification",
                    "variant": "optimal",
                    "n_bins": 4,
                    "n_estimators": 100,
                    "max_depth": None,
                    "seed": 43,
                    "roc_auc_mean": 0.97,
                    "roc_auc_std": 0.01,
                    "accuracy_mean": 0.95,
                    "accuracy_std": 0.01,
                    "macro_f1_mean": 0.94,
                    "macro_f1_std": 0.01,
                    "disc_fit_time_mean": 0.02,
                    "disc_fit_time_std": 0.002,
                    "disc_transform_time_mean": 0.001,
                    "disc_transform_time_std": 0.0,
                    "rf_fit_time_mean": 0.3,
                    "rf_fit_time_std": 0.03,
                    "rf_predict_time_mean": 0.005,
                    "rf_predict_time_std": 0.0,
                    "total_time_mean": 0.326,
                    "total_time_std": 0.03,
                },
            ],
        },
    }
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(record))
        fh.write("\n")


class TestBenchmarkRunner:
    def test_produces_jsonl_file(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        assert output.exists(), "JSONL output file was not created."

    def test_jsonl_has_one_line(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        lines = [ln for ln in output.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1, f"Expected exactly one JSONL line, got {len(lines)}."

    def test_jsonl_line_is_valid_json(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        line = next(ln for ln in output.read_text().splitlines() if ln.strip())
        payload = json.loads(line)
        assert isinstance(payload, dict)

    def test_required_metadata_fields(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        payload = json.loads(next(ln for ln in output.read_text().splitlines() if ln.strip()))
        for field in ("timestamp_utc", "commit", "repeats", "cv_folds", "seed", "platform", "results"):
            assert field in payload, f"Missing required metadata field: {field!r}"

    def test_results_contain_dataset(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        payload = json.loads(next(ln for ln in output.read_text().splitlines() if ln.strip()))
        assert "synth_clf" in payload["results"], "synth_clf should be in results"

    def test_result_rows_have_metrics(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        payload = json.loads(next(ln for ln in output.read_text().splitlines() if ln.strip()))
        rows = payload["results"]["synth_clf"]
        assert rows, "Expected at least one result row for synth_clf"
        row = rows[0]
        for key in ("total_time_mean", "rf_fit_time_mean", "disc_fit_time_mean"):
            assert key in row, f"Missing metric key: {key!r}"

    def test_classification_has_roc_auc(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        payload = json.loads(next(ln for ln in output.read_text().splitlines() if ln.strip()))
        rows = payload["results"]["synth_clf"]
        for row in rows:
            assert "roc_auc_mean" in row, "Classification row missing roc_auc_mean"

    def test_appends_on_second_run(self, tmp_path: Path) -> None:
        output = tmp_path / "test_runs.jsonl"
        _run_minimal_benchmark(output)
        _run_minimal_benchmark(output)
        lines = [ln for ln in output.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2, "Expected two JSONL lines after two runs."


class TestCompareScript:
    def test_load_runs_returns_rows(self, tmp_path: Path) -> None:
        input_path = tmp_path / "runs.jsonl"
        _write_minimal_jsonl(input_path)
        rows = load_runs(input_path)
        assert len(rows) >= 2

    def test_load_runs_has_required_fields(self, tmp_path: Path) -> None:
        input_path = tmp_path / "runs.jsonl"
        _write_minimal_jsonl(input_path)
        rows = load_runs(input_path)
        for row in rows:
            assert "variant" in row
            assert "dataset" in row

    def test_print_summary_runs_without_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        input_path = tmp_path / "runs.jsonl"
        _write_minimal_jsonl(input_path)
        rows = load_runs(input_path)
        print_summary(rows, speed_metric="total_time")
        captured = capsys.readouterr()
        assert "breast_cancer" in captured.out

    def test_pareto_front_basic(self) -> None:
        points = [
            {"speed": 1.0, "quality": 0.9},
            {"speed": 2.0, "quality": 0.95},
            {"speed": 1.5, "quality": 0.85},  # dominated
        ]
        flags = pareto_front(points, speed_key="speed", quality_key="quality", higher_quality_better=True)
        assert flags[0] is True
        assert flags[1] is True
        assert flags[2] is False

    def test_load_runs_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_runs(tmp_path / "nonexistent.jsonl")


class TestDatasetRegistry:
    def test_registry_contains_expected_names(self) -> None:
        expected = {"breast_cancer", "wine", "synth_clf", "diabetes", "synth_reg"}
        assert expected.issubset(set(DATASET_REGISTRY.keys()))

    def test_load_synth_clf(self) -> None:
        X, y, task = load_single_dataset("synth_clf")
        assert task == "classification"
        assert X.shape[0] == y.shape[0]

    def test_load_synth_reg(self) -> None:
        X, y, task = load_single_dataset("synth_reg")
        assert task == "regression"
        assert X.shape[0] == y.shape[0]

    def test_load_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown dataset"):
            load_single_dataset("nonexistent_dataset")
