"""Tests for the check that a pull request with a change that users can see adds a changelog fragment."""

import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- the tests build a real git repository to diff
from pathlib import Path

import pytest
from scripts import check_fragment


@pytest.mark.parametrize(
    "path",
    ["src/pkg/domain/summary.py", "src/pkg/py.typed"],
)
def test_package_files_are_user_visible(path: str) -> None:
    assert check_fragment.is_user_visible(path)


@pytest.mark.parametrize(
    "path",
    ["tests/unit/pkg/test_init.py", "scripts/release.py", "README.md"],
)
def test_tests_and_docs_are_not_user_visible(path: str) -> None:
    assert not check_fragment.is_user_visible(path)


@pytest.mark.parametrize("path", ["changelog.d/20261025_x.md", "changelog.d/a.md"])
def test_a_markdown_file_in_the_fragment_directory_is_a_fragment(path: str) -> None:
    assert check_fragment.is_fragment(path)


@pytest.mark.parametrize("path", ["changelog.d/README.md", "changelog.d/notes.txt", "docs/x.md"])
def test_other_files_are_not_fragments(path: str) -> None:
    assert not check_fragment.is_fragment(path)


def test_a_user_visible_change_without_a_fragment_is_a_problem() -> None:
    problem = check_fragment.fragment_problem(["src/pkg/a.py", "tests/unit/x.py"], [])
    assert problem is not None
    assert "  src/pkg/a.py\n" in problem
    assert "tests/unit/x.py" not in problem


def test_a_user_visible_change_with_a_fragment_passes() -> None:
    assert check_fragment.fragment_problem(["src/pkg/a.py"], ["changelog.d/a.md"]) is None


def test_the_readme_of_the_fragments_is_not_a_fragment() -> None:
    assert check_fragment.fragment_problem(["src/pkg/a.py"], ["changelog.d/README.md"]) is not None


def test_an_internal_change_needs_no_fragment() -> None:
    assert check_fragment.fragment_problem(["tests/unit/x.py", "README.md"], []) is None


GIT = shutil.which("git") or "git"


def git(repo: Path, *args: str) -> None:
    subprocess.run([GIT, "-C", str(repo), *args], check=True, capture_output=True)  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed git argv in a temporary repository


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "README.md").write_text("x")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_main_fails_without_a_fragment(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    assert check_fragment.main(["main"]) == 1
    assert "src/pkg/a.py" in capsys.readouterr().err


def test_main_passes_with_a_fragment(repo: Path) -> None:
    (repo / "changelog.d").mkdir()
    (repo / "changelog.d" / "a.md").write_text("### Added\n\n- A.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    assert check_fragment.main(["main"]) == 0
