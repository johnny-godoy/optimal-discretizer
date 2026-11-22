"""Fail when ``CHANGELOG.md``, the changelog fragments and the version in ``pyproject.toml`` do not agree.

Each pull request with a user-visible change adds a fragment to ``changelog.d/`` with ``scriv create``. After the merge,
the release workflow raises the version, and ``scriv collect`` moves the fragments into ``CHANGELOG.md`` under a heading
``## [X.Y.Z] - YYYY-MM-DD``. This check fails when:

- ``CHANGELOG.md`` has an ``[Unreleased]`` heading or lacks the scriv insert marker,
- a heading is not a version with a date, or the versions do not decrease from top to bottom,
- a fragment has no category, or a category that ``[tool.scriv]`` does not list,
- the version in ``pyproject.toml`` is lower than the newest heading, or higher with no fragment to release.

Run it from the repo root: ``uv run python -m scripts.check_changelog``.
"""

import re
import sys
import tomllib
from collections.abc import Collection, Mapping
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSERT_MARKER = "<!-- scriv-insert-here -->"
HEADING: re.Pattern[str] = re.compile(r"^## \[(?P<name>[^\]]+)\](?: - (?P<date>\S+))?\s*$", re.MULTILINE)
CATEGORY: re.Pattern[str] = re.compile(r"^### (?P<name>.+?)\s*$", re.MULTILINE)
COMMENT: re.Pattern[str] = re.compile(r"<!--.*?-->", re.DOTALL)
VERSION: re.Pattern[str] = re.compile(r"(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)")

type Version = tuple[int, int, int]


def parse_version(text: str) -> Version | None:
    """Read a ``MAJOR.MINOR.PATCH`` version.

    Parameters
    ----------
    text: str
        The version as written.

    Returns
    -------
    Version | None
        The three numbers, or ``None`` if the text is not a version of that form.

    """
    match = VERSION.fullmatch(text)
    if match is None:
        return None
    return int(match["major"]), int(match["minor"]), int(match["patch"])


def format_version(version: Version) -> str:
    """Write a version as ``MAJOR.MINOR.PATCH``.

    Parameters
    ----------
    version: Version
        The three numbers.

    Returns
    -------
    str
        The version text.

    """
    return ".".join(map(str, version))


def _is_iso_date(text: str | None) -> bool:
    """Tell whether a heading date is a valid ``YYYY-MM-DD`` date.

    Parameters
    ----------
    text: str | None
        The date of the heading, or ``None`` if the heading has no date.

    Returns
    -------
    bool
        True for a valid date in the ``YYYY-MM-DD`` form.

    """
    if text is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def released_versions(changelog: str) -> list[Version]:
    """List the versions of the release headings, from top to bottom.

    Parameters
    ----------
    changelog: str
        The content of ``CHANGELOG.md``.

    Returns
    -------
    list[Version]
        The version of each heading that is a valid version.

    """
    return [version for heading in HEADING.finditer(changelog) if (version := parse_version(heading["name"]))]


def heading_problems(changelog: str) -> list[str]:
    """List the problems of the headings of the changelog.

    Parameters
    ----------
    changelog: str
        The content of ``CHANGELOG.md``.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    problems: list[str] = []
    if INSERT_MARKER not in changelog:
        problems.append(f"CHANGELOG.md lacks the line {INSERT_MARKER}, where scriv collect inserts a release")
    previous: Version | None = None
    for heading in HEADING.finditer(changelog):
        name = heading["name"]
        if name.lower() == "unreleased":
            problems.append("CHANGELOG.md has an [Unreleased] section: put each change in a fragment with scriv create")
            continue
        version = parse_version(name)
        if version is None:
            problems.append(f"heading [{name}] is not a MAJOR.MINOR.PATCH version")
            continue
        if not _is_iso_date(heading["date"]):
            problems.append(f"heading [{name}] needs a release date in the form ' - YYYY-MM-DD'")
        if previous is not None and version >= previous:
            problems.append(f"heading [{name}] must be lower than the heading above it")
        previous = version
    return problems


def fragment_categories(text: str) -> list[str]:
    """List the categories of a fragment, without the categories inside HTML comments.

    Parameters
    ----------
    text: str
        The content of the fragment.

    Returns
    -------
    list[str]
        The name of each ``###`` heading, in order.

    """
    return [match["name"] for match in CATEGORY.finditer(COMMENT.sub("", text))]


def fragment_problems(name: str, text: str, categories: Collection[str]) -> list[str]:
    """List the problems of one changelog fragment.

    Parameters
    ----------
    name: str
        The file name of the fragment, for the messages.
    text: str
        The content of the fragment.
    categories: Collection[str]
        The categories that ``[tool.scriv]`` lists.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    found = fragment_categories(text)
    if not found:
        return [f"changelog.d/{name} has no category: uncomment one '### <Category>' section of the template"]
    return [
        f"changelog.d/{name} has the category '{category}', which is not one of: {', '.join(categories)}"
        for category in found
        if category not in categories
    ]


def version_problems(version: str, newest: Version | None, *, has_fragments: bool) -> list[str]:
    """List the problems of the version in ``pyproject.toml``.

    The version equals the newest heading, or it is higher when a pull request completes a milestone of ``ROADMAP.md``
    and sets the version of the milestone. A higher version needs a fragment, because the release workflow then
    releases the fragments under that version.

    Parameters
    ----------
    version: str
        The ``version`` in ``pyproject.toml``.
    newest: Version | None
        The version of the newest heading, or ``None`` if the changelog has none.
    has_fragments: bool
        Whether ``changelog.d/`` holds a fragment.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    parsed = parse_version(version)
    if parsed is None:
        return [f"pyproject.toml has version {version}, which is not a MAJOR.MINOR.PATCH version"]
    if newest is None or parsed == newest:
        return []
    if parsed < newest:
        return [f"pyproject.toml has version {version}, lower than the newest heading [{format_version(newest)}]"]
    if not has_fragments:
        return [f"pyproject.toml has version {version}, higher than the newest heading, but no fragment to release"]
    return []


def read_fragments(directory: Path) -> dict[str, str]:
    """Read the changelog fragments.

    Parameters
    ----------
    directory: Path
        The fragment directory of scriv.

    Returns
    -------
    dict[str, str]
        The content of each fragment, by file name. ``README.md`` is not a fragment.

    """
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.md"))
        if path.name.lower() != "readme.md"
    }


def changelog_problems(
    changelog: str,
    version: str,
    fragments: Mapping[str, str],
    categories: Collection[str],
) -> list[str]:
    """List every way in which the changelog, the fragments and the version break the release rule.

    Parameters
    ----------
    changelog: str
        The content of ``CHANGELOG.md``.
    version: str
        The ``version`` in ``pyproject.toml``.
    fragments: Mapping[str, str]
        The content of each fragment, by file name.
    categories: Collection[str]
        The categories that ``[tool.scriv]`` lists.

    Returns
    -------
    list[str]
        One message for each problem. The list is empty when everything agrees.

    """
    problems = heading_problems(changelog)
    for name, text in fragments.items():
        problems += fragment_problems(name, text, categories)
    released = released_versions(changelog)
    newest = released[0] if released else None
    return problems + version_problems(version, newest, has_fragments=bool(fragments))


def main() -> int:
    """Report every problem of the changelog.

    Returns
    -------
    int
        The process exit code: 0 if everything agrees, 1 otherwise.

    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scriv = pyproject["tool"]["scriv"]
    problems = changelog_problems(
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
        pyproject["project"]["version"],
        read_fragments(ROOT / scriv["fragment_directory"]),
        scriv["categories"],
    )
    for problem in problems:
        sys.stderr.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
