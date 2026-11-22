"""Tests for the check that removes ``exclude-newer-package`` exemptions once they are not needed."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from scripts import check_exclusions

NOW: datetime = datetime(2026, 10, 23, tzinfo=UTC)
LOCK = """version = 1

[[package]]
name = "Pillow"
version = "13.0.0"
sdist = { url = "u", upload-time = "2026-10-16T22:15:24.000000Z" }
wheels = [
    { url = "w", upload-time = "2026-10-17T01:00:00.000000Z" },
]

[[package]]
name = "old.pkg"
version = "1.0"
sdist = { url = "u", upload-time = "2026-01-01T00:00:00.000000Z" }

[[package]]
name = "no-files"
version = "1.0"
"""


def pyproject(exempt: dict[str, bool], span: str = "7 days") -> dict[str, Any]:
    return {"tool": {"uv": {"exclude-newer": span, "exclude-newer-package": exempt}}}


@pytest.mark.parametrize(("span", "days"), [("7 days", 7), ("1 day", 1), ("2 weeks", 14)])
def test_cutoff_days(span: str, days: int) -> None:
    assert check_exclusions.cutoff_days(span) == days


@pytest.mark.parametrize("span", ["2026-10-16T00:00:00Z", "soon", "7 hours"])
def test_cutoff_days_rejects_what_is_not_a_span_of_days(span: str) -> None:
    with pytest.raises(ValueError, match="exclude-newer must be a span"):
        check_exclusions.cutoff_days(span)


def test_newest_upload_uses_the_newest_file_and_a_normalized_name() -> None:
    uploads = check_exclusions.newest_upload(LOCK)
    assert uploads["pillow"] == datetime(2026, 10, 17, 1, tzinfo=UTC)
    assert uploads["old-pkg"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert "no-files" not in uploads


def test_an_exemption_is_kept_while_the_locked_version_is_inside_the_cutoff() -> None:
    assert check_exclusions.stale_exemptions(pyproject({"pillow": False}), LOCK, NOW) == []


def test_an_exemption_expires_once_the_locked_version_is_older_than_the_cutoff() -> None:
    later = datetime(2026, 10, 24, 1, 0, 1, tzinfo=UTC)
    [problem] = check_exclusions.stale_exemptions(pyproject({"pillow": False}), LOCK, later)
    assert "pillow: the locked version is older than the 7 days cutoff (uploaded 2026-10-17)" in problem


def test_an_exemption_expires_exactly_at_the_cutoff() -> None:
    at_cutoff = datetime(2026, 10, 24, 1, tzinfo=UTC)
    assert check_exclusions.stale_exemptions(pyproject({"pillow": False}), LOCK, at_cutoff)


def test_an_exemption_for_a_package_that_is_not_locked_is_stale() -> None:
    [problem] = check_exclusions.stale_exemptions(pyproject({"Gone_Pkg": False}), LOCK, NOW)
    assert problem.startswith("Gone_Pkg: not in uv.lock")


def test_a_project_without_exemptions_has_nothing_to_check() -> None:
    assert check_exclusions.stale_exemptions({}, LOCK, NOW) == []
    assert check_exclusions.stale_exemptions(pyproject({}, span="soon"), LOCK, NOW) == []


def test_main_reports_stale_exemptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\nexclude-newer = "7 days"\nexclude-newer-package = { "old-pkg" = false }\n',
    )
    (tmp_path / "uv.lock").write_text(LOCK)
    monkeypatch.setattr(check_exclusions, "ROOT", tmp_path)
    assert check_exclusions.main() == 1
    assert "old-pkg: the locked version is older" in capsys.readouterr().err


def test_main_passes_without_exemptions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.uv]\n")
    (tmp_path / "uv.lock").write_text(LOCK)
    monkeypatch.setattr(check_exclusions, "ROOT", tmp_path)
    assert check_exclusions.main() == 0
