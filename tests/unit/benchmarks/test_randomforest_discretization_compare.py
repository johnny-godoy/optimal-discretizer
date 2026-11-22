"""Tests of the comparison of RandomForest discretization runs."""

from pathlib import Path
from typing import Any

import orjson
import pytest
from benchmarks import randomforest_discretization_compare as compare


def row(dataset: str, task: str, variant: str, n_bins: int | None, measured: tuple[float, float]) -> dict[str, Any]:
    quality, speed = measured
    quality_key = "roc_auc_mean" if task == "classification" else "r2_mean"
    return {
        "dataset": dataset,
        "task": task,
        "variant": variant,
        "n_bins": n_bins,
        quality_key: quality,
        "total_time_mean": speed,
        "disc_fit_time_mean": 0.0 if variant == "none" else speed / 10,
    }


def write_run(path: Path, rows: list[dict[str, Any]]) -> None:
    results: dict[str, list[dict[str, Any]]] = {}
    for record in rows:
        results.setdefault(record["dataset"], []).append(record)
    with path.open("ab") as handle:
        handle.write(orjson.dumps({"timestamp_utc": "2026-01-01T00:00:00+00:00", "commit": "abc", "results": results}))
        handle.write(b"\n\n")


ROWS = [
    row("wine", "classification", "none", None, (0.95, 0.30)),
    row("wine", "classification", "optimal", 4, (0.97, 0.20)),
    row("wine", "classification", "kmeans", 4, (0.96, 0.25)),
    row("wine", "classification", "quantile", 4, (0.94, 0.22)),
    row("wine", "classification", "optimal", 8, (0.93, 0.21)),
    row("wine", "classification", "kmeans", 8, (0.92, 0.26)),
    row("wine", "classification", "quantile", 8, (0.91, 0.23)),
    row("diabetes", "regression", "none", None, (0.50, 0.10)),
    row("diabetes", "regression", "optimal", 4, (0.40, 0.05)),
]


def test_load_runs_flattens_the_rows_of_each_dataset(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    write_run(path, ROWS)
    rows = compare.load_runs(path)
    assert len(rows) == len(ROWS)
    assert all(record["commit"] == "abc" for record in rows)


def test_load_runs_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compare.load_runs(tmp_path / "missing.jsonl")


def test_load_runs_rejects_a_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    path.write_bytes(b"{not json\n")
    with pytest.raises(ValueError, match="Invalid JSON at line 1"):
        compare.load_runs(path)


def test_pareto_front_keeps_the_points_that_no_point_dominates() -> None:
    points = [{"speed": 1.0, "quality": 0.9}, {"speed": 0.5, "quality": 0.8}, {"speed": 2.0, "quality": 0.7}]
    assert compare.pareto_front(points, "speed", "quality") == [True, True, False]
    assert compare.pareto_front(points, "speed", "quality", higher_quality_better=False) == [False, True, True]


def test_the_summary_answers_the_three_questions(capsys: pytest.CaptureFixture[str]) -> None:
    compare.print_summary(ROWS, speed_metric="total_time")
    out = capsys.readouterr().out
    assert "═══ wine (classification) ═══" in out
    assert "1. optimal vs kmeans: optimal wins quality in 2/2 bin-count comparisons; wins speed in 2/2" in out
    assert "2. optimal vs quantile: optimal wins quality in 2/2 comparisons" in out
    assert "3. Discretized variants beating none (ROC-AUC=0.9500): optimal@n_bins=4(0.9700), kmeans" not in out
    assert "kmeans@n_bins=4(0.9600), optimal@n_bins=4(0.9700)" in out
    assert "3. No discretized variant beats none (R²=0.5000)" in out
    assert "1. optimal vs kmeans: insufficient data" in out


def test_the_summary_of_no_rows_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    compare.print_summary([], speed_metric="total_time")
    assert "No records found." in capsys.readouterr().out


def test_a_dataset_without_the_raw_forest_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    compare.print_summary([row("wine", "classification", "optimal", 4, (0.9, 0.1))], speed_metric="total_time")
    out = capsys.readouterr().out
    assert "3. 'none' variant not present" in out
    assert "2. optimal vs quantile: insufficient data." in out


def test_a_dataset_without_the_speed_metric_has_no_aggregate(capsys: pytest.CaptureFixture[str]) -> None:
    compare.print_summary(ROWS, speed_metric="rf_fit_time")
    assert "No aggregated data available." in capsys.readouterr().out


def test_without_plotly_no_plot_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compare, "go", None)
    assert compare.generate_plots(ROWS, tmp_path, "total_time") == []


def test_main_prints_the_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "runs.jsonl"
    write_run(path, ROWS)
    assert compare.app(["--input-path", str(path), "--plots", "--plot-dir", str(tmp_path / "plots")]) == 0
    assert "Loaded records: 9" in capsys.readouterr().out
