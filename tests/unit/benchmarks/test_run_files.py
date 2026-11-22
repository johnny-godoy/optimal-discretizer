"""Tests of the run files that the benchmark scripts share."""

from pathlib import Path

import numpy as np
import orjson
from benchmarks.run_files import append_jsonl, dumps, resolve_git_commit


def make_git_dir(root: Path, head: str) -> Path:
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(head, encoding="utf-8")
    return git_dir


def test_a_detached_head_names_its_commit(tmp_path: Path) -> None:
    make_git_dir(tmp_path, "abc123\n")
    assert resolve_git_commit(tmp_path) == "abc123"


def test_a_branch_reads_its_reference_file(tmp_path: Path) -> None:
    git_dir = make_git_dir(tmp_path, "ref: refs/heads/main\n")
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "refs" / "heads" / "main").write_text("def456\n", encoding="utf-8")
    assert resolve_git_commit(tmp_path) == "def456"


def test_a_packed_branch_reads_packed_refs(tmp_path: Path) -> None:
    git_dir = make_git_dir(tmp_path, "ref: refs/heads/main\n")
    (git_dir / "packed-refs").write_text(
        "# pack-refs with: peeled\nbad-line\n111 refs/heads/other\n222 refs/heads/main\n^333\n",
        encoding="utf-8",
    )
    assert resolve_git_commit(tmp_path) == "222"


def test_a_missing_reference_is_unknown(tmp_path: Path) -> None:
    git_dir = make_git_dir(tmp_path, "ref: refs/heads/main\n")
    assert resolve_git_commit(tmp_path) == "unknown"
    (git_dir / "packed-refs").write_text("111 refs/heads/other\n", encoding="utf-8")
    assert resolve_git_commit(tmp_path) == "unknown"


def test_no_git_directory_is_unknown(tmp_path: Path) -> None:
    assert resolve_git_commit(tmp_path) == "unknown"


def test_runs_append_one_line_each(tmp_path: Path) -> None:
    output = tmp_path / "runs" / "file.jsonl"
    append_jsonl(output, dumps({"run": 1}))
    append_jsonl(output, dumps({"run": 2, "values": np.array([1.5, 2.0])}))
    lines = output.read_bytes().splitlines()
    assert [orjson.loads(line) for line in lines] == [{"run": 1}, {"run": 2, "values": [1.5, 2.0]}]
