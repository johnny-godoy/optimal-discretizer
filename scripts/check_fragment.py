"""Fail when a pull request changes the package but adds no changelog fragment.

A change to the package code (``src/``) can reach users, so it needs a fragment in ``changelog.d/``. A pull request
whose change is internal (a refactor, a test-only edit) carries the label ``no-changelog`` instead, and the workflow
``.github/workflows/changelog.yml`` then skips this check. Run it from the repo root:
``uv run python -m scripts.check_fragment <base revision>``.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import] -- git offers the changed paths of a branch only as a command
import sys
from collections.abc import Iterable, Sequence

USER_VISIBLE = ("src/",)
FRAGMENT_DIRECTORY = "changelog.d/"


def is_user_visible(path: str) -> bool:
    """Tell whether a changed file can change what users of the package get.

    Parameters
    ----------
    path: str
        The path of the file, relative to the repo root.

    Returns
    -------
    bool
        True for a file of the package.

    """
    return path.startswith(USER_VISIBLE)


def is_fragment(path: str) -> bool:
    """Tell whether an added file is a changelog fragment.

    Parameters
    ----------
    path: str
        The path of the file, relative to the repo root.

    Returns
    -------
    bool
        True for a Markdown file in ``changelog.d/`` other than its README.

    """
    name = path.removeprefix(FRAGMENT_DIRECTORY)
    return path.startswith(FRAGMENT_DIRECTORY) and name.endswith(".md") and name.lower() != "readme.md"


def fragment_problem(changed: Iterable[str], added: Iterable[str]) -> str | None:
    """Check that a change that users can see comes with a fragment.

    Parameters
    ----------
    changed: Iterable[str]
        The paths that the pull request changes.
    added: Iterable[str]
        The paths that the pull request adds.

    Returns
    -------
    str | None
        The problem, or ``None`` if there is none.

    """
    visible = sorted(path for path in changed if is_user_visible(path))
    if not visible or any(is_fragment(path) for path in added):
        return None
    listed = "\n".join(f"  {path}" for path in visible)
    return (
        "This pull request changes files that users can see, but adds no changelog fragment:\n"
        f"{listed}\n"
        "Run `uv run scriv create` and describe the change, or add the label no-changelog if users see no change."
    )


def _git_paths(base: str, diff_filter: str) -> list[str]:
    """List the paths that changed between the merge base with ``base`` and ``HEAD``.

    Parameters
    ----------
    base: str
        The revision of the base branch.
    diff_filter: str
        The ``--diff-filter`` of ``git diff``, for example ``A`` for added files.

    Returns
    -------
    list[str]
        The paths.

    """
    command = ["git", "diff", "--name-only", f"--diff-filter={diff_filter}", f"{base}...HEAD"]
    result = subprocess.run(command, capture_output=True, text=True, check=True)  # ruff: ignore[subprocess-without-shell-equals-true] -- a fixed git argv; the base revision comes from the workflow
    return result.stdout.split()


def main(argv: Sequence[str]) -> int:
    """Report a missing fragment.

    Parameters
    ----------
    argv: Sequence[str]
        The command line arguments: the revision of the base branch.

    Returns
    -------
    int
        The process exit code: 0 if no fragment is missing, 1 otherwise.

    """
    [base] = argv
    problem = fragment_problem(_git_paths(base, "ACDMR"), _git_paths(base, "A"))
    if problem is None:
        return 0
    sys.stderr.write(f"{problem}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
