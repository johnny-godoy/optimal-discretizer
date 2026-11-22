"""Tests for the check that the changelog, its fragments and the version agree."""

from pathlib import Path

import pytest
from scripts import check_changelog

CATEGORIES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
HEADER = "# Changelog\n\nIntro text.\n\n<!-- scriv-insert-here -->\n\n"
RELEASED = HEADER + "## [0.0.3] - 2026-10-25\n\n### Added\n\n- New.\n\n## [0.0.2] - 2026-10-23\n\n- Old.\n"
FRAGMENT = "<!--\n### Removed\n\n- Template.\n-->\n### Added\n\n- A feature.\n"


def problems(changelog: str, version: str, fragments: dict[str, str] | None = None) -> list[str]:
    return check_changelog.changelog_problems(changelog, version, fragments or {}, CATEGORIES)


def test_a_changelog_whose_newest_heading_is_the_version_passes() -> None:
    assert problems(RELEASED, "0.0.3") == []


def test_pending_fragments_with_the_released_version_pass() -> None:
    assert problems(RELEASED, "0.0.3", {"a.md": FRAGMENT}) == []


def test_an_unreleased_section_fails_because_changes_belong_in_fragments() -> None:
    changelog = HEADER + "## [Unreleased]\n\n### Added\n\n- Waiting.\n\n## [0.0.3] - 2026-10-25\n"
    [problem] = problems(changelog, "0.0.3")
    assert problem.startswith("CHANGELOG.md has an [Unreleased] section")


def test_an_empty_unreleased_heading_also_fails() -> None:
    assert problems(HEADER + "## [unreleased]\n\n## [0.0.3] - 2026-10-25\n", "0.0.3")


def test_a_changelog_without_the_insert_marker_fails() -> None:
    [problem] = problems(RELEASED.replace("<!-- scriv-insert-here -->\n", ""), "0.0.3")
    assert problem.startswith("CHANGELOG.md lacks the line <!-- scriv-insert-here -->")


@pytest.mark.parametrize("heading", ["## [0.0.4]", "## [0.0.4] - 2026-13-01", "## [0.0.4] - 25/10/2026"])
def test_a_heading_without_a_valid_date_fails(heading: str) -> None:
    changelog = HEADER + heading + "\n\n" + RELEASED.removeprefix(HEADER)
    [problem] = problems(changelog, "0.0.4")
    assert problem == "heading [0.0.4] needs a release date in the form ' - YYYY-MM-DD'"


@pytest.mark.parametrize("name", ["1.0", "v1.0.0", "01.0.0"])
def test_a_heading_that_is_not_a_version_fails(name: str) -> None:
    changelog = HEADER + f"## [{name}] - 2026-10-26\n\n" + RELEASED.removeprefix(HEADER)
    assert problems(changelog, "0.0.3") == [f"heading [{name}] is not a MAJOR.MINOR.PATCH version"]


@pytest.mark.parametrize("below", ["0.0.3", "0.0.4", "1.0.0"])
def test_headings_must_decrease(below: str) -> None:
    changelog = HEADER + f"## [0.0.3] - 2026-10-25\n\n## [{below}] - 2026-10-24\n"
    [problem] = problems(changelog, "0.0.3")
    assert problem == f"heading [{below}] must be lower than the heading above it"


def test_versions_compare_as_numbers_not_as_text() -> None:
    assert problems(HEADER + "## [0.10.0] - 2026-10-25\n\n## [0.9.0] - 2026-10-24\n", "0.10.0") == []


def test_a_changelog_without_releases_passes_because_a_new_project_has_none() -> None:
    assert problems(HEADER, "0.0.0") == []


def test_a_version_below_the_newest_heading_fails() -> None:
    [problem] = problems(RELEASED, "0.0.2")
    assert problem == "pyproject.toml has version 0.0.2, lower than the newest heading [0.0.3]"


def test_a_milestone_version_above_the_newest_heading_passes_with_a_fragment() -> None:
    assert problems(RELEASED, "0.1.0", {"a.md": FRAGMENT}) == []


def test_a_raised_version_without_a_fragment_fails() -> None:
    [problem] = problems(RELEASED, "0.1.0")
    assert problem == "pyproject.toml has version 0.1.0, higher than the newest heading, but no fragment to release"


def test_a_version_that_is_not_semver_fails() -> None:
    [problem] = problems(RELEASED, "0.0.3rc1")
    assert problem == "pyproject.toml has version 0.0.3rc1, which is not a MAJOR.MINOR.PATCH version"


def test_the_template_left_commented_is_a_fragment_without_a_category() -> None:
    [problem] = problems(RELEASED, "0.0.3", {"empty.md": "<!--\n### Added\n\n- Template.\n-->\n"})
    assert problem.startswith("changelog.d/empty.md has no category")


def test_a_fragment_with_an_unknown_category_fails() -> None:
    [problem] = problems(RELEASED, "0.0.3", {"a.md": "### Breaking\n\n- X.\n"})
    assert problem.startswith("changelog.d/a.md has the category 'Breaking', which is not one of: Added")


def test_fragment_categories_skip_commented_sections() -> None:
    assert check_changelog.fragment_categories(FRAGMENT + "\n### Fixed\n\n- B.\n") == ["Added", "Fixed"]


def test_read_fragments_skips_the_readme_and_other_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "b.md").write_text("B")
    (tmp_path / "a.md").write_text("A")
    (tmp_path / ".gitkeep").write_text("")
    assert check_changelog.read_fragments(tmp_path) == {"a.md": "A", "b.md": "B"}


def test_format_version_writes_the_three_numbers() -> None:
    assert check_changelog.format_version((1, 10, 0)) == "1.10.0"


def write_project(root: Path, version: str, changelog: str, fragments: dict[str, str]) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n\n[tool.scriv]\nfragment_directory = "changelog.d"\n'
        f"categories = {list(CATEGORIES)!r}\n".replace("'", '"'),
    )
    (root / "CHANGELOG.md").write_text(changelog)
    (root / "changelog.d").mkdir()
    for name, text in fragments.items():
        (root / "changelog.d" / name).write_text(text)


def test_main_reports_problems(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_project(tmp_path, "0.0.3", RELEASED, {"bad.md": "### Breaking\n"})
    monkeypatch.setattr(check_changelog, "ROOT", tmp_path)
    assert check_changelog.main() == 1
    assert "changelog.d/bad.md has the category 'Breaking'" in capsys.readouterr().err


def test_main_passes_for_a_consistent_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(tmp_path, "0.0.3", RELEASED, {"a.md": FRAGMENT})
    monkeypatch.setattr(check_changelog, "ROOT", tmp_path)
    assert check_changelog.main() == 0
