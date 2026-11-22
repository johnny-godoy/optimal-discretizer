"""Run a command with a fixed argument list, and return its output.

The release scripts start ``uv``, ``git`` and the Python of a new environment. Each call passes an argument list that
the script builds, and never a shell line. This module holds the one ``subprocess`` import of these scripts, so the
ignores for it stand in one place.
"""

import os
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- the one module of the release scripts that starts a command from a fixed argument list
from collections.abc import Mapping, Sequence

import attrs


@attrs.frozen
class CommandResult:
    """The outcome of a command that ended.

    Attributes
    ----------
    returncode : int
        The exit code.
    stdout : str
        The standard output.
    stderr : str
        The standard error.

    """

    returncode: int
    stdout: str
    stderr: str


def run_fixed(
    argv: Sequence[str | os.PathLike[str]],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run a command from a fixed argument list, with no shell, and capture its output.

    Parameters
    ----------
    argv : Sequence[str | os.PathLike[str]]
        The command and its arguments.
    cwd : str | os.PathLike[str] | None
        The working directory, or ``None`` for the current one.
    env : Mapping[str, str] | None
        The environment variables, or ``None`` for those of this process.

    Returns
    -------
    CommandResult
        The exit code and the output.

    """
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- the callers build the argument list; no shell reads it
        [os.fspath(word) for word in argv],
        cwd=cwd,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
