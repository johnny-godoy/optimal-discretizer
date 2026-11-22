"""Check the subject style and the size of commits, beyond the grammar that ``cz check`` checks.

``cz check`` checks that a commit message is a conventional commit (``type(scope)!: description``). This script checks
two more rules of ``.claude/rules/commits-and-prs.md``:

- The description starts with a lower-case word and has no period at the end.
- A commit changes at most ``MAX_CHANGED_LINES`` lines, without generated files, because a small commit has one
  purpose and a reviewer can read it. A larger commit needs the trailer ``Large-Commit: <reason>``, for example a file
  move or a generated test fixture.

Run it as a ``commit-msg`` hook (``--message-file``), or on the commits of a branch (``--base``). Merge commits and the
commits that git writes for ``fixup!`` and ``squash!`` are skipped.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- git offers the commits of a branch only as a command
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

MAX_CHANGED_LINES = 400
# the same minimum as the reason of a workaround in scripts/check_ignores.py
MIN_REASON_WORDS = 4
SKIPPED_PREFIXES = ("Merge ", "Revert ", "fixup! ", "squash! ")
# generated or collected files: their size says nothing about the size of the change
GENERATED: re.Pattern[str] = re.compile(r"^(uv\.lock|CHANGELOG\.md|changelog\.d/.*|notebooks/__marimo__/.*)$")
SUBJECT: re.Pattern[str] = re.compile(r"^[a-z]+(\([^)]+\))?!?: (?P<description>.+)$")
CAPITALIZED_WORD: re.Pattern[str] = re.compile(r"^[A-Z][a-z]+\b")
LARGE_COMMIT: re.Pattern[str] = re.compile(r"^Large-Commit: (?P<reason>.+)$", re.MULTILINE)
GIT = shutil.which("git") or "git"


def subject_problems(subject: str) -> list[str]:
    """List the style problems of the first line of a commit message.

    Parameters
    ----------
    subject: str
        The first line of the commit message.

    Returns
    -------
    list[str]
        One message for each problem. A subject that ``cz check`` rejects has none here, because ``cz check`` reports
        it.

    """
    if subject.startswith(SKIPPED_PREFIXES):
        return []
    match = SUBJECT.match(subject)
    if match is None:
        return []
    description = match["description"]
    problems = []
    if CAPITALIZED_WORD.match(description):
        problems.append(f"'{subject}': start the description with a lower-case word")
    if description.endswith("."):
        problems.append(f"'{subject}': remove the period at the end of the description")
    return problems


def changed_lines(numstat: str) -> int:
    """Count the changed lines of a commit, without the generated files.

    Parameters
    ----------
    numstat: str
        The output of ``git show --numstat --format=``: added lines, deleted lines and the path, one file per line.

    Returns
    -------
    int
        The added plus the deleted lines. A binary file (``-`` counts) adds nothing.

    """
    total = 0
    for line in numstat.splitlines():
        added, deleted, path = line.split("\t", 2)
        if not GENERATED.match(path) and added.isdigit() and deleted.isdigit():
            total += int(added) + int(deleted)
    return total


def size_problem(subject: str, message: str, lines: int) -> str | None:
    """Check the size of a commit.

    Parameters
    ----------
    subject: str
        The first line of the commit message, for the report.
    message: str
        The whole commit message, which may hold a ``Large-Commit`` trailer.
    lines: int
        The changed lines of the commit, from ``changed_lines``.

    Returns
    -------
    str | None
        The problem, or ``None`` if there is none.

    """
    if lines <= MAX_CHANGED_LINES:
        return None
    trailer = LARGE_COMMIT.search(message)
    if trailer is not None and len(trailer["reason"].split()) >= MIN_REASON_WORDS:
        return None
    return (
        f"'{subject}' changes {lines} lines (limit {MAX_CHANGED_LINES}, without generated files). Split it into "
        "commits with one purpose each, or add the trailer 'Large-Commit: <reason of at least 4 words>'."
    )


def _git(*args: str) -> str:
    """Run git and return its output.

    Parameters
    ----------
    *args: str
        The git arguments.

    Returns
    -------
    str
        The standard output.

    """
    result = subprocess.run([GIT, *args], capture_output=True, text=True, check=True)  # ruff: ignore[subprocess-without-shell-equals-true] -- a fixed git argv; the base revision comes from the workflow
    return result.stdout


def branch_problems(base: str) -> list[str]:
    """List the problems of each commit between ``base`` and ``HEAD``, without merge commits.

    Parameters
    ----------
    base: str
        The revision of the base branch.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    problems: list[str] = []
    for sha in _git("rev-list", "--no-merges", f"{base}..HEAD").split():
        message = _git("log", "-1", "--format=%B", sha)
        subject = message.split("\n", 1)[0]
        if subject.startswith(SKIPPED_PREFIXES):
            continue
        problems += subject_problems(subject)
        size = size_problem(subject, message, changed_lines(_git("show", "--numstat", "--format=", sha)))
        if size is not None:
            problems.append(size)
    return problems


def _report(problems: Iterable[str]) -> int:
    """Write the problems to standard error.

    Parameters
    ----------
    problems: Iterable[str]
        The messages.

    Returns
    -------
    int
        The process exit code: 0 if there is no problem, 1 otherwise.

    """
    found = list(problems)
    for problem in found:
        sys.stderr.write(f"{problem}\n")
    return 1 if found else 0


def main(argv: Sequence[str]) -> int:
    """Check one commit message, or every commit of a branch.

    Parameters
    ----------
    argv: Sequence[str]
        ``--message-file PATH`` (the ``commit-msg`` hook) or ``--base REV`` (CI).

    Returns
    -------
    int
        The process exit code: 0 if there is no problem, 1 otherwise.

    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message-file", type=Path, help="the file that holds the commit message")
    mode.add_argument("--base", help="check every commit from this revision to HEAD")
    args = parser.parse_args(argv)
    if args.base is not None:
        return _report(branch_problems(args.base))
    subject = args.message_file.read_text(encoding="utf-8").split("\n", 1)[0]
    return _report(subject_problems(subject))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
