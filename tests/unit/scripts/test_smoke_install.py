"""Tests for the smoke test of an installed distribution."""

from pathlib import Path

import pytest
from scripts import smoke_install
from scripts.fixed_command import CommandResult


def fake_which(name: str) -> str:
    return f"/usr/bin/{name}"


def no_command(name: str) -> None:
    del name


def test_a_file_is_installed_by_its_absolute_path(tmp_path: Path) -> None:
    wheel = tmp_path / "optimal_discretizer-1.0.0-cp313-cp313-linux_x86_64.whl"
    wheel.touch()
    command = smoke_install.install_command("uv", tmp_path / "venv", str(wheel))
    assert command[:3] == ["uv", "pip", "install"]
    assert command[-1] == str(wheel.resolve())
    assert command[command.index("--resolution") + 1] == "highest"


def test_a_published_version_is_installed_by_its_requirement(tmp_path: Path) -> None:
    command = smoke_install.install_command("uv", tmp_path / "venv", "optimal-discretizer==1.0.0", "lowest-direct")
    assert command[-1] == "optimal-discretizer==1.0.0"
    assert command[command.index("--resolution") + 1] == "lowest-direct"


def test_the_clean_environment_has_an_empty_home(tmp_path: Path) -> None:
    variables = smoke_install.clean_environment(tmp_path)
    assert variables["HOME"] == str(tmp_path)
    assert variables["PYTHONNOUSERSITE"] == "1"


def test_the_clean_environment_keeps_the_windows_system_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    assert smoke_install.clean_environment(tmp_path)["SYSTEMROOT"] == "C:\\Windows"


def test_the_steps_run_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_run(argv: list[str], *, cwd: Path, env: dict[str, str] | None) -> CommandResult:
        del cwd, env
        commands.append(list(argv))
        return CommandResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smoke_install, "run_fixed", fake_run)
    monkeypatch.setattr(smoke_install.shutil, "which", fake_which)
    assert smoke_install.app(["optimal-discretizer==1.0.0", "1.0.0", "--python", "3.12"]) == 0
    assert commands[0][:4] == ["/usr/bin/uv", "venv", "--python", "3.12"]
    assert commands[1][-1] == "optimal-discretizer==1.0.0"
    assert commands[2][1:3] == ["-I", "-c"]
    assert commands[2][-1] == "1.0.0"


def test_a_failed_step_stops_with_its_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_install, "run_fixed", lambda *_, **__: CommandResult(1, "", "no such version"))  # pyrefly: ignore[implicit-any-lambda] -- the fake takes any arguments of run_fixed and ignores them
    monkeypatch.setattr(smoke_install.shutil, "which", fake_which)
    with pytest.raises(SystemExit, match="no such version"):
        smoke_install.app(["optimal-discretizer==9.9.9", "9.9.9"])


def test_without_uv_the_test_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_install.shutil, "which", no_command)
    with pytest.raises(SystemExit, match="the uv command is not on the path"):
        smoke_install.app(["optimal-discretizer==1.0.0", "1.0.0"])


def test_the_environment_python_follows_the_platform(tmp_path: Path) -> None:
    python = smoke_install.environment_python(tmp_path)
    assert python.parent.name in {"bin", "Scripts"}
