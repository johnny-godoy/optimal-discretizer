"""Tests for the check of the files of the built distributions."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts import check_distributions
from scripts.fixed_command import CommandResult

GOOD_WHEEL = [
    "optimal_discretizer/__init__.py",
    "optimal_discretizer/py.typed",
    "optimal_discretizer/domain/optimal_partition.cpython-313-x86_64-linux-gnu.so",
]
GOOD_SDIST = ["pyproject.toml", "meson.build", "src/optimal_discretizer/domain/optimal_partition.pyx"]


def write_wheel(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "")
    return path


def write_sdist(path: Path, names: list[str]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            info = tarfile.TarInfo(f"optimal_discretizer-1.0.0/{name}")
            archive.addfile(info, io.BytesIO(b""))
    return path


def test_a_good_wheel_has_no_problem() -> None:
    assert check_distributions.wheel_problems(GOOD_WHEEL) == []


def test_a_windows_wheel_has_a_pyd_kernel() -> None:
    names = [*GOOD_WHEEL[:2], "optimal_discretizer/domain/optimal_partition.cp313-win_amd64.pyd"]
    assert check_distributions.wheel_problems(names) == []


@pytest.mark.parametrize(
    "source",
    ["optimal_discretizer/domain/optimal_partition.c", "optimal_discretizer/domain/optimal_partition.pyx"],
)
def test_a_wheel_with_a_source_of_the_kernel_fails(source: str) -> None:
    assert check_distributions.wheel_problems([*GOOD_WHEEL, source]) == [
        f"{source}: a wheel ships no source of the kernel",
    ]


def test_a_wheel_without_the_kernel_fails() -> None:
    problems = check_distributions.wheel_problems(GOOD_WHEEL[:2])
    assert problems == ["the compiled kernel optimal_discretizer/domain/optimal_partition is missing"]


def test_a_wheel_without_py_typed_fails() -> None:
    assert check_distributions.wheel_problems([GOOD_WHEEL[0], GOOD_WHEEL[2]]) == [
        "optimal_discretizer/py.typed is missing",
    ]


def test_a_source_distribution_with_a_generated_file_fails() -> None:
    names = [*GOOD_SDIST, "src/optimal_discretizer/domain/optimal_partition.c", "build/kernel.so"]
    assert check_distributions.sdist_problems(names) == [
        "src/optimal_discretizer/domain/optimal_partition.c: a source distribution ships no generated or compiled file",
        "build/kernel.so: a source distribution ships no generated or compiled file",
    ]


def test_a_source_distribution_without_the_cython_source_fails() -> None:
    assert check_distributions.sdist_problems(GOOD_SDIST[:2]) == [
        "src/optimal_discretizer/domain/optimal_partition.pyx is missing",
    ]


def test_main_reads_the_files_of_a_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_wheel(tmp_path / "optimal_discretizer-1.0.0-cp313-cp313-linux_x86_64.whl", GOOD_WHEEL)
    write_sdist(tmp_path / "optimal_discretizer-1.0.0.tar.gz", [*GOOD_SDIST, "src/x.c"])
    assert check_distributions.app([str(tmp_path)]) == 1
    assert capsys.readouterr().out == (
        "optimal_discretizer-1.0.0.tar.gz: src/x.c: a source distribution ships no generated or compiled file\n"
    )


def test_main_fails_on_an_empty_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_distributions.app([str(tmp_path)]) == 1
    assert "no wheel and no source distribution" in capsys.readouterr().out


def test_git_mode_lists_the_tracked_c_files(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_git(argv: list[str], *, cwd: Path) -> CommandResult:
        assert argv == ["git", "ls-files", "*.c"]
        assert cwd == Path.cwd()
        return CommandResult(returncode=0, stdout="src/kernel.c\n", stderr="")

    monkeypatch.setattr(check_distributions, "run_fixed", fake_git)
    assert check_distributions.app(["--git"]) == 1
    assert capsys.readouterr().out == "src/kernel.c: git tracks a generated C file\n"


def test_this_repository_tracks_no_c_file() -> None:
    assert check_distributions.git_problems(Path(__file__).resolve().parents[3]) == []
