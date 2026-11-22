"""Print the version that the release workflow gives to the pending changelog fragments.

The release workflow runs this after each merge to ``main``. If ``changelog.d/`` holds no fragment, it prints nothing,
and nothing is released. Else it prints the next version, by the table of
``.claude/rules/changelog-and-versioning.md``:

- A version in ``pyproject.toml`` above the newest ``CHANGELOG.md`` heading is a milestone of ``ROADMAP.md``, which the
  pull request set. It is used as it is.
- Before 1.0.0, every release raises the PATCH number.
- From 1.0.0, a fragment with a ``Removed`` category or a ``**BREAKING:**`` entry raises the MAJOR number, a fragment
  with ``Added``, ``Changed`` or ``Deprecated`` raises the MINOR number, and any other fragment raises the PATCH number.

The script fails if ``scripts.check_changelog`` finds a problem. Run it from the repo root:
``uv run python -m scripts.release``.
"""

import re
import sys
import tomllib
from collections.abc import Iterable, Mapping

from scripts import check_changelog
from scripts.check_changelog import Version

# the version of a project that has no release yet
FIRST: Version = (0, 0, 0)
MAJOR_CATEGORIES = frozenset({"Removed"})
MINOR_CATEGORIES = frozenset({"Added", "Changed", "Deprecated"})
# a breaking entry starts with **BREAKING:** (the changelog style) or **BREAKING**
BREAKING_MARK: re.Pattern[str] = re.compile(r"\*\*BREAKING:?\*\*")


def bump(newest: Version, fragments: Iterable[str]) -> Version:
    """Raise a released version by the largest change that the fragments hold.

    Parameters
    ----------
    newest: Version
        The version of the newest ``CHANGELOG.md`` heading.
    fragments: Iterable[str]
        The content of each pending fragment.

    Returns
    -------
    Version
        The next version.

    """
    major, minor, patch = newest
    if major == 0:
        return major, minor, patch + 1
    texts = list(fragments)
    categories = {category for text in texts for category in check_changelog.fragment_categories(text)}
    if categories & MAJOR_CATEGORIES or any(
        BREAKING_MARK.search(check_changelog.COMMENT.sub("", text)) for text in texts
    ):
        return major + 1, 0, 0
    if categories & MINOR_CATEGORIES:
        return major, minor + 1, 0
    return major, minor, patch + 1


def next_version(version: Version, newest: Version, fragments: Mapping[str, str]) -> Version | None:
    """Choose the version of the next release.

    Parameters
    ----------
    version: Version
        The ``version`` in ``pyproject.toml``.
    newest: Version
        The version of the newest ``CHANGELOG.md`` heading.
    fragments: Mapping[str, str]
        The content of each pending fragment, by file name.

    Returns
    -------
    Version | None
        The next version, or ``None`` if no fragment waits for a release.

    """
    if not fragments:
        return None
    if version > newest:
        return version
    return bump(newest, fragments.values())


def main() -> int:
    """Print the next version, or nothing if no fragment waits for a release.

    Returns
    -------
    int
        The process exit code: 0 on success, 1 if the changelog check finds a problem.

    """
    if check_changelog.main():
        return 1
    root = check_changelog.ROOT
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    fragments = check_changelog.read_fragments(root / pyproject["tool"]["scriv"]["fragment_directory"])
    version = check_changelog.parse_version(pyproject["project"]["version"])
    released = check_changelog.released_versions((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    # the changelog check passed, so the version is valid
    if version is None:
        return 1
    # a project with no release yet starts from 0.0.0, so its first release is 0.0.1 or its milestone version
    chosen = next_version(version, released[0] if released else FIRST, fragments)
    if chosen is not None:
        sys.stdout.write(f"{check_changelog.format_version(chosen)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
