"""Tests for the choice of the next version from the pending changelog fragments."""

from pathlib import Path

import pytest
from scripts import check_changelog, release

from tests.unit.scripts.test_check_changelog import RELEASED, write_project

ADDED = "### Added\n\n- A feature.\n"
FIXED = "### Fixed\n\n- A bug.\n"
REMOVED = "### Removed\n\n- A function.\n"
BREAKING = "### Changed\n\n- **BREAKING:** A new signature.\n"


@pytest.mark.parametrize("fragment", [ADDED, FIXED, REMOVED, BREAKING])
def test_before_1_0_0_every_release_raises_the_patch(fragment: str) -> None:
    assert release.bump((0, 2, 5), [fragment]) == (0, 2, 6)


@pytest.mark.parametrize("fragment", [REMOVED, BREAKING])
def test_from_1_0_0_a_breaking_change_raises_the_major(fragment: str) -> None:
    assert release.bump((1, 2, 3), [FIXED, fragment]) == (2, 0, 0)


@pytest.mark.parametrize("category", ["Added", "Changed", "Deprecated"])
def test_from_1_0_0_a_feature_raises_the_minor(category: str) -> None:
    assert release.bump((1, 2, 3), [FIXED, f"### {category}\n\n- X.\n"]) == (1, 3, 0)


@pytest.mark.parametrize("category", ["Fixed", "Security"])
def test_from_1_0_0_a_fix_raises_the_patch(category: str) -> None:
    assert release.bump((1, 2, 3), [f"### {category}\n\n- X.\n"]) == (1, 2, 4)


def test_a_commented_breaking_category_does_not_count() -> None:
    assert release.bump((1, 2, 3), ["<!--\n### Removed\n\n- X.\n-->\n" + FIXED]) == (1, 2, 4)


def test_no_fragment_means_no_release() -> None:
    assert release.next_version((0, 0, 3), (0, 0, 3), {}) is None


def test_a_milestone_version_set_by_the_pull_request_is_kept() -> None:
    assert release.next_version((0, 1, 0), (0, 0, 3), {"a.md": FIXED}) == (0, 1, 0)


def test_the_released_version_is_raised_by_the_fragments() -> None:
    assert release.next_version((0, 0, 3), (0, 0, 3), {"a.md": ADDED}) == (0, 0, 4)


@pytest.mark.parametrize(
    "case",
    [("0.0.3", {"a.md": ADDED}, "0.0.4\n"), ("0.1.0", {"a.md": ADDED}, "0.1.0\n"), ("0.0.3", {}, "")],
)
def test_main_prints_the_next_version(
    case: tuple[str, dict[str, str], str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    version, fragments, printed = case
    write_project(tmp_path, version, RELEASED, fragments)
    monkeypatch.setattr(check_changelog, "ROOT", tmp_path)
    assert release.main() == 0
    assert capsys.readouterr().out == printed


@pytest.mark.parametrize(("version", "printed"), [("0.0.0", "0.0.1\n"), ("0.1.0", "0.1.0\n")])
def test_main_releases_the_first_version_of_a_changelog_without_releases(
    version: str,
    printed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_project(tmp_path, version, RELEASED.split("## [", 1)[0], {"a.md": ADDED})
    monkeypatch.setattr(check_changelog, "ROOT", tmp_path)
    assert release.main() == 0
    assert capsys.readouterr().out == printed


def test_main_fails_when_the_changelog_check_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(tmp_path, "0.0.2", RELEASED, {"a.md": ADDED})
    monkeypatch.setattr(check_changelog, "ROOT", tmp_path)
    assert release.main() == 1


def test_a_breaking_mark_inside_a_comment_does_not_count() -> None:
    assert release.bump((1, 2, 3), ["<!-- **BREAKING:** draft -->\n" + FIXED]) == (1, 2, 4)
