"""Tests of the comparison of k-means effectiveness runs."""

from pathlib import Path

import orjson
import pytest
from benchmarks import kmeans_effectiveness_compare as compare


def metrics(optimality: float, gap: float, mean_ms: float) -> dict[str, float]:
    return {"optimality_pct": optimality, "mean_gap_pct": gap, "mean_ms": mean_ms, "median_ms": mean_ms}


def write_runs(path: Path) -> None:
    runs = [
        {
            "timestamp_utc": "2026-01-02T00:00:00+00:00",
            "commit": "b" * 40,
            "repeats": 1,
            "problems": {
                "small": {"main": metrics(100.0, 0.0, 0.02), "lloyd": metrics(90.0, 1.0, 4.0)},
            },
        },
        {
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "commit": "unknown",
            "repeats": 1,
            "problems": {
                "small": {"main": metrics(100.0, 0.0, 0.03), "lloyd": metrics(80.0, 2.0, 4.0)},
            },
        },
    ]
    path.write_bytes(b"\n".join(orjson.dumps(run) for run in runs) + b"\n\n")


def test_load_runs_sorts_by_time(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    write_runs(path)
    runs = compare.load_runs(path)
    assert [run.short_commit for run in runs] == ["unknown", "bbbbbbb"]
    assert runs[1].main_mean_ms == pytest.approx(0.02)
    assert runs[1].lloyd_optimality_mean_pct == pytest.approx(90.0)


def test_load_runs_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compare.load_runs(tmp_path / "missing.jsonl")


def test_load_runs_rejects_a_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    path.write_bytes(b'{"commit": "x"}\n')
    with pytest.raises(ValueError, match="Invalid run payload at line 1"):
        compare.load_runs(path)


def test_main_ranks_the_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "runs.jsonl"
    write_runs(path)
    assert compare.app(["--input-path", str(path), "--plot-dir", str(tmp_path / "plots")]) == 0
    out = capsys.readouterr().out
    assert "bbbbbbb" in out
