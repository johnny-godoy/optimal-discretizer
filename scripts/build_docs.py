"""Build or serve the documentation with Zensical, after the proof papers are exported.

Run it from the repo root: ``uv run --group docs python -m scripts.build_docs [build|serve]``. CI runs the same
command, so a local build fails exactly when CI fails.

The proof papers of ``proofs/papers/<topic>/paper.typ`` are compiled into ``docs/proofs/<topic>.pdf``, and the proof
pages link to them.

Zensical prints a ``griffe:`` warning for a docstring that does not render, for example a parameter that the function
does not have, and still exits with code 0. The ``build`` command fails when the output has such a warning.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- marimo and Zensical only offer their build as a command
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import structlog
import typst

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PAPERS_ROOT = ROOT / "proofs" / "papers"
PAPER_DIR = ROOT / "docs" / "proofs"
WARNING_PREFIX = "griffe:"


def export_papers() -> None:
    """Compile each proof paper of ``proofs/papers/`` into ``docs/proofs/<topic>.pdf``.

    The paper of a topic imports the shared style of ``proofs/papers/``, so that folder is the root of the compilation.
    Compiling takes a second, so the function compiles every paper on every call. A paper that does not compile fails
    the build.

    """
    for paper in sorted(PAPERS_ROOT.glob("*/paper.typ")):
        PAPER_DIR.mkdir(parents=True, exist_ok=True)
        typst.compile(paper, output=PAPER_DIR / f"{paper.parent.name}.pdf", root=PAPERS_ROOT)


def find_warnings(output: str) -> list[str]:
    """Find the docstring warnings in the output of a Zensical build.

    Parameters
    ----------
    output: str
        The text that the build printed.

    Returns
    -------
    list[str]
        The lines that start with ``griffe:``, in order.

    """
    return [line for line in output.splitlines() if line.startswith(WARNING_PREFIX)]


def build() -> int:
    """Build the site in strict mode, and fail on a docstring warning.

    Returns
    -------
    int
        The exit code: the code of Zensical if it fails, 1 if the output has a warning, and 0 otherwise.

    """
    export_papers()
    command = [sys.executable, "-m", "zensical", "build", "--strict"]
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv from sys.executable, never untrusted input
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    # one text for both streams, so the gate sees the warnings wherever Zensical writes them
    output = result.stdout + result.stderr
    sys.stdout.write(output)
    if result.returncode:
        return result.returncode
    warnings = find_warnings(output)
    for warning in warnings:
        logger.error("docstring warning", warning=warning)
    return int(bool(warnings))


def serve() -> int:
    """Start the preview server of Zensical.

    Returns
    -------
    int
        The exit code of the server.

    """
    export_papers()
    command = [sys.executable, "-m", "zensical", "serve"]
    return subprocess.run(command, cwd=ROOT, check=False).returncode  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv from sys.executable, never untrusted input


COMMANDS: dict[str, Callable[[], int]] = {"build": build, "serve": serve}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command of the script.

    Parameters
    ----------
    argv: Sequence[str] | None
        The arguments of the command line, without the program name. ``None`` reads ``sys.argv``.

    Returns
    -------
    int
        The exit code of the command.

    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("command", nargs="?", default="build", choices=sorted(COMMANDS))
    return COMMANDS[parser.parse_args(argv).command]()


if __name__ == "__main__":
    sys.exit(main())
