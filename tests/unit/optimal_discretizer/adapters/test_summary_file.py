"""Tests for the JSON file of a summary."""

from pathlib import Path

from optimal_discretizer.adapters.summary_file import read_summary, write_summary
from optimal_discretizer.domain.summary import Summary

SUMMARY: Summary = Summary(count=2, minimum=1.0, maximum=3.0, mean=2.0)


def test_write_summary_writes_indented_json(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    write_summary(SUMMARY, path)
    assert path.read_text(encoding="utf-8") == (
        '{\n  "count": 2,\n  "minimum": 1.0,\n  "maximum": 3.0,\n  "mean": 2.0\n}'
    )


def test_read_summary_returns_what_write_summary_wrote(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    write_summary(SUMMARY, path)
    assert read_summary(path) == SUMMARY


def test_read_summary_accepts_a_string_path(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_bytes(b'{"count": 1, "minimum": 4.0, "maximum": 4.0, "mean": 4.0}')
    assert read_summary(str(path)) == Summary(count=1, minimum=4.0, maximum=4.0, mean=4.0)
