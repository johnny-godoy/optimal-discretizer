"""Install a distribution into a clean virtual environment and run a smoke test of the installed package.

A green test suite of the source checkout does not show that a user can install the release. This script installs a
wheel, a source distribution or a published version in a new environment, and it runs the smoke test with no source
checkout on the path. The release workflow runs it on the built files before the upload, and on the published version
after the upload.

The smoke test checks that the installed version is the expected one, that ``optimal_discretizer`` comes from the
environment and not from a checkout, that the kernel is a compiled extension module, that ``kmeans_1d`` finds the
optimum of a small problem that a search over every partition also solves, and that the example of the README runs.

Run it from the repo root:
``uv run python -m scripts.smoke_install dist/optimal_discretizer-1.2.3-cp313-cp313-manylinux_x86_64.whl 1.2.3``.
"""

import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

import cyclopts

from scripts.fixed_command import run_fixed

SMOKE_PROGRAM = """
import importlib.machinery
import importlib.metadata
import itertools
import sys

import numpy as np

import optimal_discretizer
from optimal_discretizer import OptimalDiscretizer, kmeans_1d
from optimal_discretizer.domain import optimal_partition

expected_version = sys.argv[1]
installed_version = importlib.metadata.version("optimal-discretizer")
assert installed_version == expected_version, f"installed {installed_version}, expected {expected_version}"
location = optimal_discretizer.__file__
assert "site-packages" in location, f"not imported from the environment: {location}"
suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
assert optimal_partition.__file__.endswith(suffixes), f"the kernel is not compiled: {optimal_partition.__file__}"

values = np.array([4.0, 1.0, 9.5, 2.0, 10.0, 3.5, 20.0, 1.5])
best = min(
    sum(float(np.square(part - part.mean()).sum()) for part in np.split(np.sort(values), list(cuts)))
    for cuts in itertools.combinations(range(1, values.size), 2)
)
inertia = kmeans_1d(values, 3).inertia
assert abs(inertia - best) < 1e-9, f"kmeans_1d gave {inertia}, the search over every partition gave {best}"

features = np.random.default_rng(0).normal(size=(200, 3))
bins = OptimalDiscretizer(n_bins=5).fit_transform(features)
assert bins.shape == (200, 3) and set(np.unique(bins)) <= {0.0, 1.0, 2.0, 3.0, 4.0}
print(f"smoke test passed: optimal-discretizer {installed_version}")
"""


def clean_environment(home: Path) -> dict[str, str]:
    """Build the environment of the smoke test: an empty home directory and no user site packages.

    Parameters
    ----------
    home : Path
        An empty directory to use as the home directory.

    Returns
    -------
    dict[str, str]
        The environment variables for the new interpreter.

    """
    variables = {"HOME": str(home), "PATH": os.pathsep.join(["/usr/bin", "/bin"]), "PYTHONNOUSERSITE": "1"}
    # Windows needs its system root to start an interpreter.
    if "SYSTEMROOT" in os.environ:
        variables["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return variables


def environment_python(environment: Path) -> Path:
    """Return the interpreter of a virtual environment.

    Parameters
    ----------
    environment : Path
        The virtual environment.

    Returns
    -------
    Path
        Its Python executable.

    """
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    return scripts / ("python.exe" if os.name == "nt" else "python")


def install_command(
    uv: str,
    environment: Path,
    requirement: str,
    resolution: Literal["highest", "lowest-direct"] = "highest",
) -> list[str]:
    """Write the command that installs the distribution into the environment.

    Parameters
    ----------
    uv : str
        The path of the ``uv`` command.
    environment : Path
        The virtual environment.
    requirement : str
        A path of a wheel or a source distribution, or a requirement such as ``optimal-discretizer==1.2.3``.
    resolution : Literal["highest", "lowest-direct"]
        ``"highest"`` installs the newest release of each dependency that the requirements allow. ``"lowest-direct"``
        installs the oldest release that each direct requirement allows, to test the lower bounds.

    Returns
    -------
    list[str]
        The arguments of the command.

    """
    target = str(Path(requirement).resolve()) if Path(requirement).exists() else requirement
    python = str(environment_python(environment))
    return [uv, "pip", "install", "--refresh", "--resolution", resolution, "--python", python, target]


def _run(command: Sequence[str], *, environment: Mapping[str, str] | None, working_directory: Path) -> None:
    """Run a command and stop with its output if it fails.

    Parameters
    ----------
    command : Sequence[str]
        The command and its arguments.
    environment : Mapping[str, str] | None
        The environment variables, or ``None`` for those of this process.
    working_directory : Path
        The directory to run in. It holds no source of ``optimal_discretizer``.

    Raises
    ------
    SystemExit
        If the command fails. The message holds its output.

    """
    result = run_fixed(command, cwd=working_directory, env=environment)
    sys.stdout.write(result.stdout)
    if result.returncode:
        message = f"command failed with exit code {result.returncode}: {' '.join(command[:4])} ...\n{result.stderr}"
        raise SystemExit(message)


app: cyclopts.App = cyclopts.App(
    name="smoke_install",
    help=__doc__.splitlines()[0] if __doc__ else None,
    result_action="return_value",
)


@app.default
def smoke_install(
    requirement: str,
    expected_version: str,
    *,
    python: str = "3.13",
    resolution: Literal["highest", "lowest-direct"] = "highest",
) -> int:
    """Install a distribution in a clean environment and test the installed package.

    Parameters
    ----------
    requirement : str
        A path of a wheel or a source distribution, or a requirement such as ``optimal-discretizer==1.2.3``.
    expected_version : str
        The version that the installed package must report.
    python : str
        The Python version of the new environment. A wheel must be built for it.
    resolution : Literal["highest", "lowest-direct"]
        Which release of each dependency to install. ``"lowest-direct"`` tests the lower bounds of the requirements.

    Returns
    -------
    int
        0 if the smoke test passes.

    Raises
    ------
    SystemExit
        If ``uv`` is missing or a step fails. The message holds the output of the step.

    """
    uv = shutil.which("uv")
    if uv is None:
        message = "the uv command is not on the path"
        raise SystemExit(message)
    with tempfile.TemporaryDirectory(prefix="optimal-discretizer-smoke-") as directory:
        workspace = Path(directory)
        environment = workspace / "venv"
        home = workspace / "home"
        home.mkdir()
        _run([uv, "venv", "--python", python, str(environment)], environment=None, working_directory=workspace)
        _run(install_command(uv, environment, requirement, resolution), environment=None, working_directory=workspace)
        _run(
            [str(environment_python(environment)), "-I", "-c", SMOKE_PROGRAM, expected_version],
            environment=clean_environment(home),
            working_directory=home,
        )
    return 0


if __name__ == "__main__":
    sys.exit(app())
