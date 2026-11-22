"""Fail when a change adds a copy-paste clone to the package in ``src``.

The ``jscpd`` hook of ``prek.toml`` keeps the share of duplicated lines under 1%. That limit lets a small new clone
pass, so this check compares the clones of the working tree with the clones of a base revision. It fails on each clone
that the base lacks, and it ignores the clones that the base already has.

The check scans the package, the ``root_package`` of ``[tool.importlinter]`` in ``pyproject.toml``. It uses the
options of the hook (python, 50 tokens, 5 lines) for both trees, so the check changes the policy and not the detector.

Run it from the repo root: ``uv run python -m scripts.check_new_clones [--base origin/main]``.

The base revision must exist in the local clone. If it does not, the check fails with the command that fetches it. It
never passes silently. In CI, ``actions/checkout`` has a shallow history, so the workflow fetches the base branch first.
For an offline workflow, ``jscpd --baseline FILE`` with a committed baseline file is the other mode of ``jscpd``. Do
not combine the two modes.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- jscpd runs on Node.js and git answers revision questions only as commands
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Keep this version equal to the one in the jscpd hook of prek.toml. A unit test checks that the two agree.
JSCPD_VERSION = "5.4.2"
DEFAULT_BASE = "origin/main"
BASE_ENVIRONMENT_VARIABLE = "NEW_CLONES_BASE"
SETUP_EXIT_CODE = 2

Runner = Callable[[Sequence[str], Path], int]


def scan_path(root: Path) -> str:
    """Find the package that the check scans.

    Parameters
    ----------
    root: Path
        The repo root.

    Returns
    -------
    str
        The path of the package, relative to the root, for example ``src/package``.

    """
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return f"src/{pyproject['tool']['importlinter']['root_package']}"


def jscpd_command(base: str, executable: str, path: str) -> list[str]:
    """Build the ``jscpd`` command line that fails on a new clone.

    Parameters
    ----------
    base: str
        The base revision, for example ``origin/main``.
    executable: str
        The path of ``npx``.
    path: str
        The path of the package, relative to the repo root.

    Returns
    -------
    list[str]
        The arguments. The path comes before ``--fail-on-new-clones``, because that option takes an optional count.

    """
    return [
        executable,
        "--yes",
        f"jscpd@{JSCPD_VERSION}",
        path,
        "--format",
        "python",
        "--min-tokens",
        "50",
        "--min-lines",
        "5",
        "--baseline-from-ref",
        base,
        "--fail-on-new-clones",
        "--reporters",
        "console",
        "--no-colors",
    ]


def run_command(command: Sequence[str], root: Path) -> int:
    """Run a command and give its exit code.

    Parameters
    ----------
    command: Sequence[str]
        The command and its arguments.
    root: Path
        The working directory.

    Returns
    -------
    int
        The exit code of the command.

    """
    return subprocess.run(command, cwd=root, check=False).returncode  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv of npx, never untrusted input


def revision_exists(base: str, root: Path) -> bool:
    """Tell whether a revision exists in the local clone.

    Parameters
    ----------
    base: str
        The revision.
    root: Path
        The repo root.

    Returns
    -------
    bool
        True if ``git`` finds a commit for the revision.

    """
    git = shutil.which("git")
    if git is None:
        return False
    command = [git, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"]
    return subprocess.run(command, cwd=root, capture_output=True, check=False).returncode == 0  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv of git, the revision is one argument


def parse_base(argv: Sequence[str]) -> str:
    """Read the base revision from the command line.

    Parameters
    ----------
    argv: Sequence[str]
        The arguments. ``--base`` names the base revision.

    Returns
    -------
    str
        The base revision. The default is the environment variable of the base revision, or ``origin/main``.

    """
    parser = argparse.ArgumentParser(prog="check_new_clones", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base",
        help=f"the base revision; the default is ${BASE_ENVIRONMENT_VARIABLE} or {DEFAULT_BASE}",
    )
    base: str | None = parser.parse_args(list(argv)).base
    return base or os.environ.get(BASE_ENVIRONMENT_VARIABLE, DEFAULT_BASE)


def main(argv: Sequence[str] = (), runner: Runner = run_command, root: Path = ROOT) -> int:
    """Run the command line.

    Parameters
    ----------
    argv: Sequence[str]
        The arguments. ``--base`` names the base revision.
    runner: Runner
        Runs the ``jscpd`` command. A test passes a fake.
    root: Path
        The repo root.

    Returns
    -------
    int
        0 if the change adds no clone, 1 if it adds a clone, and 2 if the check cannot run (no base revision, no npx).

    """
    base = parse_base(argv)
    if not revision_exists(base, root):
        remote, _, branch = base.partition("/")
        sys.stderr.write(
            f"The base revision {base!r} does not exist in this clone, so the check cannot compare clones.\n"
            f"Fetch it with `git fetch {remote} {branch or 'main'}`.\n"
            "In a shallow clone, `git fetch --unshallow` also works.\n"
            f"Name another base with --base or ${BASE_ENVIRONMENT_VARIABLE}.\n",
        )
        return SETUP_EXIT_CODE
    npx = shutil.which("npx")
    if npx is None:
        sys.stderr.write("npx is missing. Install Node.js, because jscpd runs on Node.js.\n")
        return SETUP_EXIT_CODE
    return 1 if runner(jscpd_command(base, npx, scan_path(root)), root) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
