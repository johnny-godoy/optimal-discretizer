"""Tests for the check of new copy-paste clones."""

import subprocess  # ruff: ignore[suspicious-subprocess-import] -- the tests build a small git repository with the git command
from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts import check_new_clones

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def git(root: Path, *arguments: str) -> None:
    subprocess.run([*GIT, *arguments], cwd=root, check=True, capture_output=True)  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed git argv in a test


def make_repo(root: Path) -> Path:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "pyproject.toml").write_text('[tool.importlinter]\nroot_package = "pkg"\n', encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def fake_runner(exit_code: int, commands: list[Sequence[str]]) -> check_new_clones.Runner:
    def run(command: Sequence[str], _root: Path) -> int:
        commands.append(command)
        return exit_code

    return run


def test_command_puts_the_path_before_the_fail_option() -> None:
    command = check_new_clones.jscpd_command("origin/main", "/bin/npx", "src/pkg")
    assert command[:3] == ["/bin/npx", "--yes", f"jscpd@{check_new_clones.JSCPD_VERSION}"]
    assert command[3] == "src/pkg"
    assert command.index("src/pkg") < command.index("--fail-on-new-clones")
    assert command[command.index("--baseline-from-ref") + 1] == "origin/main"
    assert command[command.index("--min-tokens") + 1] == "50"
    assert command[command.index("--min-lines") + 1] == "5"


def test_version_and_options_equal_the_jscpd_hook() -> None:
    # prek.toml uses multi-line inline tables (TOML 1.1), which tomllib cannot read, so the test reads the text.
    hooks = (check_new_clones.ROOT / "prek.toml").read_text(encoding="utf-8")
    assert f'additional_dependencies = ["jscpd@{check_new_clones.JSCPD_VERSION}"]' in hooks
    entry = next(line for line in hooks.splitlines() if line.strip().startswith('entry = "jscpd '))
    command = check_new_clones.jscpd_command("base", "npx", "src/pkg")
    for name, value in (("--format", "python"), ("--min-tokens", "50"), ("--min-lines", "5")):
        assert f"{name} {value}" in entry
        assert command[command.index(name) + 1] == value


def test_revision_exists(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    assert check_new_clones.revision_exists("main", root)
    assert not check_new_clones.revision_exists("origin/main", root)


def test_missing_base_fails_with_the_fetch_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    commands: list[Sequence[str]] = []
    root = make_repo(tmp_path / "repo")
    assert check_new_clones.main(["--base", "origin/main"], fake_runner(0, commands), root) == 2
    assert "git fetch origin main" in capsys.readouterr().err
    assert commands == []


def test_base_comes_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(check_new_clones.BASE_ENVIRONMENT_VARIABLE, "main")
    commands: list[Sequence[str]] = []
    assert check_new_clones.main([], fake_runner(0, commands), make_repo(tmp_path / "repo")) == 0
    assert "main" in commands[0]
    assert "src/pkg" in commands[0]


@pytest.mark.parametrize(("jscpd_exit", "expected"), [(0, 0), (1, 1)])
def test_exit_code_follows_jscpd(tmp_path: Path, jscpd_exit: int, expected: int) -> None:
    assert (
        check_new_clones.main(["--base", "main"], fake_runner(jscpd_exit, []), make_repo(tmp_path / "repo")) == expected
    )


def test_missing_npx_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_repo(tmp_path / "repo")
    real_which = check_new_clones.shutil.which

    def which(name: str) -> str | None:
        return None if name == "npx" else real_which(name)

    monkeypatch.setattr(check_new_clones.shutil, "which", which)
    assert check_new_clones.main(["--base", "main"], fake_runner(0, []), root) == check_new_clones.SETUP_EXIT_CODE
    assert "npx is missing" in capsys.readouterr().err


def test_missing_git_means_no_revision(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:

    def which(_name: str) -> None:
        return None

    monkeypatch.setattr(check_new_clones.shutil, "which", which)
    assert not check_new_clones.revision_exists("main", tmp_path)


def test_default_runner_gives_the_exit_code_of_the_command(tmp_path: Path) -> None:
    assert check_new_clones.run_command(["git", "--version"], tmp_path) == 0
    assert check_new_clones.run_command(["git", "rev-parse", "--verify", "nope"], tmp_path) != 0
