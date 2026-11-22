"""Tests for the script that builds the docs."""

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from scripts import build_docs


def touch(path: Path, mtime: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, ...]:
    """Point the paths of the script into a temporary directory.

    Returns
    -------
    tuple[Path, ...]
        The notebooks and the package modules that the export reads.

    """
    monkeypatch.setattr(build_docs, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(build_docs, "PAPER_DIR", tmp_path / "docs" / "proofs")
    del tmp_path, monkeypatch
    return ()


@pytest.fixture
def compiled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path, Path]]:
    """Replace ``typst.compile``, so that no test compiles a real paper.

    Returns
    -------
    list[tuple[Path, Path, Path]]
        The list that collects the paper, the output and the root of each call.

    """
    calls: list[tuple[Path, Path, Path]] = []

    def compile_paper(paper: Path, *, output: Path, root: Path) -> None:
        calls.append((paper, output, root))

    monkeypatch.setattr(build_docs.typst, "compile", compile_paper)
    return calls


def record_runs(monkeypatch: pytest.MonkeyPatch, result: Callable[[list[str]], int] | None = None) -> list[list[str]]:
    """Replace ``subprocess.run``.

    Returns
    -------
    list[list[str]]
        The list that collects the commands.

    """
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> build_docs.subprocess.CompletedProcess[str]:
        commands.append(command)
        code = result(command) if result else 0
        return build_docs.subprocess.CompletedProcess(command, code, stdout="", stderr="")

    monkeypatch.setattr(build_docs.subprocess, "run", run)
    return commands


def test_find_warnings_returns_the_griffe_lines() -> None:
    output = "Build started\ngriffe: a.py:1: Parameter 'x' is bad\nNo issues found\ngriffe: b.py:2: other\n"
    assert build_docs.find_warnings(output) == ["griffe: a.py:1: Parameter 'x' is bad", "griffe: b.py:2: other"]


def test_find_warnings_ignores_a_line_that_only_mentions_griffe() -> None:
    assert build_docs.find_warnings("see griffe: docs\n") == []


def test_build_fails_when_zensical_prints_a_griffe_warning_and_exits_zero(
    sources: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Zensical 0.0.71 exits with code 0 on a docstring warning; this is the bug that the gate closes.
    del sources

    def run(command: list[str], **_kwargs: object) -> build_docs.subprocess.CompletedProcess[str]:
        text = "griffe: src/x.py:1: Parameter 'bogus' does not appear in the function signature\n"
        return build_docs.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr=text if "zensical" in command else "",
        )

    monkeypatch.setattr(build_docs.subprocess, "run", run)
    assert build_docs.build() == 1
    assert "Parameter 'bogus'" in capsys.readouterr().out


def test_build_passes_when_the_output_is_clean(sources: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    del sources
    commands = record_runs(monkeypatch)
    assert build_docs.build() == 0
    assert commands[-1] == [sys.executable, "-m", "zensical", "build", "--strict"]


def test_build_returns_the_exit_code_of_zensical(sources: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    del sources
    record_runs(monkeypatch, lambda command: 3 if "zensical" in command else 0)
    assert build_docs.build() == 3


def test_serve_exports_then_starts_the_server(sources: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    del sources
    commands = record_runs(monkeypatch)
    assert build_docs.serve() == 0
    assert commands[-1] == [sys.executable, "-m", "zensical", "serve"]
    assert len(commands) == 1


def test_main_runs_build_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(build_docs.COMMANDS, "build", lambda: 7)
    assert build_docs.main([]) == 7


def test_main_runs_the_named_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(build_docs.COMMANDS, "serve", lambda: 5)
    assert build_docs.main(["serve"]) == 5


@pytest.mark.usefixtures("sources")
def test_export_papers_compiles_every_topic_into_the_docs_folder(
    tmp_path: Path,
    compiled: list[tuple[Path, Path, Path]],
) -> None:
    second = touch(tmp_path / "papers" / "second-topic" / "paper.typ", 100)
    first = touch(tmp_path / "papers" / "first-topic" / "paper.typ", 100)
    touch(tmp_path / "papers" / "style.typ", 100)
    build_docs.export_papers()

    pdfs = tmp_path / "docs" / "proofs"
    assert pdfs.is_dir()
    assert compiled == [
        (first, pdfs / "first-topic.pdf", tmp_path / "papers"),
        (second, pdfs / "second-topic.pdf", tmp_path / "papers"),
    ]


@pytest.mark.usefixtures("sources")
def test_export_papers_without_a_paper_creates_nothing(tmp_path: Path, compiled: list[tuple[Path, Path, Path]]) -> None:
    build_docs.export_papers()
    assert compiled == []
    assert not (tmp_path / "docs" / "proofs").exists()


@pytest.mark.parametrize("command", ["build", "serve"])
def test_build_and_serve_export_the_papers_before_the_site(
    command: str,
    sources: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del sources
    events = record_runs(monkeypatch)
    monkeypatch.setattr(build_docs, "export_papers", lambda: events.append(["papers"]))
    build_docs.COMMANDS[command]()
    assert [event[0] if event == ["papers"] else event[2] for event in events[-2:]] == ["papers", "zensical"]
