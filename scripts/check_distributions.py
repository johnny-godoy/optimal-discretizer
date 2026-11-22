"""Fail when a built distribution or the git index holds a file that must not ship.

Cython writes ``optimal_partition.c`` from ``optimal_partition.pyx`` at build time. The C file holds the paths of the
machine that built it and changes with each Cython version, so it belongs in no distribution and not in git. The checks:

1. ``--git``: git tracks no ``.c`` file.
2. Each wheel holds the compiled kernel (``optimal_partition`` with the suffix of an extension module), the Python
   modules and ``py.typed``, and no ``.c``, ``.pyx`` or ``meson.build`` file.
3. Each source distribution holds ``optimal_partition.pyx`` and ``meson.build``, and no ``.c`` file and no compiled
   file.

The release workflow runs it on ``dist/`` before any upload, and the ``check-distributions`` hook runs ``--git``.
Run it from the repo root: ``uv run python -m scripts.check_distributions dist`` or ``... --git``.
"""

import sys
import tarfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

import cyclopts

from scripts.fixed_command import run_fixed

GENERATED_SUFFIXES = frozenset({".c"})
COMPILED_SUFFIXES = frozenset({".so", ".pyd", ".dylib", ".o", ".obj"})
KERNEL = "optimal_discretizer/domain/optimal_partition"
WHEEL_REQUIRED = ("optimal_discretizer/__init__.py", "optimal_discretizer/py.typed")
SDIST_REQUIRED = ("src/optimal_discretizer/domain/optimal_partition.pyx", "meson.build", "pyproject.toml")


def wheel_problems(names: Sequence[str]) -> list[str]:
    """List the problems of the file names of one wheel.

    Parameters
    ----------
    names : Sequence[str]
        The names of the files in the wheel.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    problems = [f"{name}: a wheel ships no source of the kernel" for name in names if _is_source(name)]
    if not any(name.startswith(KERNEL) and PurePosixPath(name).suffix in {".so", ".pyd"} for name in names):
        problems.append(f"the compiled kernel {KERNEL} is missing")
    problems.extend(f"{required} is missing" for required in WHEEL_REQUIRED if required not in names)
    return problems


def _is_source(name: str) -> bool:
    """Tell whether a file name of a wheel is a source of the kernel.

    Returns
    -------
    bool
        ``True`` for a C file, the Cython file and the meson file.

    """
    path = PurePosixPath(name)
    return path.suffix in GENERATED_SUFFIXES or path.suffix == ".pyx" or path.name == "meson.build"


def sdist_problems(names: Sequence[str]) -> list[str]:
    """List the problems of the file names of one source distribution, without its top directory.

    Parameters
    ----------
    names : Sequence[str]
        The names of the files in the source distribution, relative to its top directory.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    problems = [
        f"{name}: a source distribution ships no generated or compiled file"
        for name in names
        if PurePosixPath(name).suffix in GENERATED_SUFFIXES | COMPILED_SUFFIXES
    ]
    problems.extend(f"{required} is missing" for required in SDIST_REQUIRED if required not in names)
    return problems


def distribution_problems(path: Path) -> list[str]:
    """List the problems of one wheel or source distribution.

    Parameters
    ----------
    path : Path
        A ``.whl`` or a ``.tar.gz`` file.

    Returns
    -------
    list[str]
        One message for each problem, with the file name in front.

    """
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            problems = wheel_problems(archive.namelist())
    else:
        with tarfile.open(path) as archive:
            names = [member.name.split("/", 1)[1] for member in archive.getmembers() if member.isfile()]
        problems = sdist_problems(names)
    return [f"{path.name}: {problem}" for problem in problems]


def git_problems(root: Path) -> list[str]:
    """List the C files that git tracks.

    Parameters
    ----------
    root : Path
        The root of the repository.

    Returns
    -------
    list[str]
        One message for each tracked C file.

    """
    result = run_fixed(["git", "ls-files", "*.c"], cwd=root)
    return [f"{name}: git tracks a generated C file" for name in result.stdout.split()]


app: cyclopts.App = cyclopts.App(
    name="check_distributions",
    help=__doc__.splitlines()[0] if __doc__ else None,
    result_action="return_value",
)


@app.default
def main(directory: Path | None = None, *, git: bool = False) -> int:
    """Check the distributions of a directory, or the files that git tracks.

    Parameters
    ----------
    directory : Path | None
        The directory with the wheels and the source distribution, for example ``dist``.
    git : bool
        Check the files that git tracks instead.

    Returns
    -------
    int
        0 if no problem is found, else 1.

    """
    problems = git_problems(Path.cwd()) if git else []
    if directory is not None:
        files = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
        if not files:
            problems.append(f"{directory}: no wheel and no source distribution")
        for path in files:
            problems.extend(distribution_problems(path))
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(app())
