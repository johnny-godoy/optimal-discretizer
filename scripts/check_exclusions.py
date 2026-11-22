"""Fail when an ``exclude-newer-package`` exemption in ``pyproject.toml`` is no longer needed.

uv skips releases that are newer than the cutoff ``exclude-newer = "N days"``. An entry in ``exclude-newer-package``
lets one package skip that rule, for example to take a security fix at once. The entry is temporary: it is redundant
when every file of the locked version is older than the cutoff, or when the package is not in the lock. This check
reads ``uv.lock`` and fails then, so the exemption is removed. Run it from the repo root:
``uv run python -m scripts.check_exclusions``.
"""

import re
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
UNIT_DAYS = {"day": 1, "days": 1, "week": 7, "weeks": 7}
SPAN: re.Pattern[str] = re.compile(r"(?P<count>\d+) (?P<unit>days?|weeks?)")
UPLOAD_TIME: re.Pattern[str] = re.compile(r'upload-time = "(?P<time>[^"]+)"')


def _normalize(name: str) -> str:
    """Return the package name in the form that PEP 503 uses to compare names.

    Parameters
    ----------
    name: str
        The package name as written.

    Returns
    -------
    str
        The name in lower case, with each run of ``-``, ``_`` and ``.`` replaced by one ``-``.

    """
    return re.sub(r"[-_.]+", "-", name).lower()


def cutoff_days(span: str) -> int:
    """Convert the ``exclude-newer`` span to a number of days.

    Parameters
    ----------
    span: str
        The value of ``exclude-newer``, for example ``"7 days"``.

    Returns
    -------
    int
        The length of the span in days.

    Raises
    ------
    ValueError
        If the value is not a span of days or weeks. An absolute date cannot expire an exemption.

    """
    match = SPAN.fullmatch(span)
    if match is None:
        msg = f'exclude-newer must be a span such as "7 days", not {span!r}'
        raise ValueError(msg)
    return int(match["count"]) * UNIT_DAYS[match["unit"]]


def newest_upload(lock_text: str) -> dict[str, datetime]:
    """Find the newest file upload time of each locked package.

    Parameters
    ----------
    lock_text: str
        The content of ``uv.lock``.

    Returns
    -------
    dict[str, datetime]
        The newest upload time of any file of the locked version, by normalized package name.

    """
    uploads: dict[str, datetime] = {}
    for block in lock_text.split("\n[[package]]\n")[1:]:
        name = re.match(r'name = "(?P<name>[^"]+)"', block)
        times = [datetime.fromisoformat(m["time"]) for m in UPLOAD_TIME.finditer(block)]
        if name is not None and times:
            uploads[_normalize(name["name"])] = max(times)
    return uploads


def stale_exemptions(pyproject: dict[str, Any], lock_text: str, now: datetime) -> list[str]:
    """List the exemptions that uv no longer needs.

    Parameters
    ----------
    pyproject: dict[str, Any]
        The parsed ``pyproject.toml``.
    lock_text: str
        The content of ``uv.lock``.
    now: datetime
        The current time, with a time zone.

    Returns
    -------
    list[str]
        One message for each exemption to remove. The list is empty when all exemptions are still needed.

    """
    uv = pyproject.get("tool", {}).get("uv", {})
    exempt = uv.get("exclude-newer-package", {})
    if not exempt:
        return []
    cutoff = now - timedelta(days=cutoff_days(uv["exclude-newer"]))
    uploads = newest_upload(lock_text)
    problems = []
    for package in exempt:
        uploaded = uploads.get(_normalize(package))
        if uploaded is None:
            problems.append(f"{package}: not in uv.lock - remove it from exclude-newer-package")
        elif uploaded <= cutoff:
            problems.append(
                f"{package}: the locked version is older than the {uv['exclude-newer']} cutoff "
                f"(uploaded {uploaded:%Y-%m-%d}) - remove it from exclude-newer-package",
            )
    return problems


def main() -> int:
    """Report every exemption that is no longer needed.

    Returns
    -------
    int
        The process exit code: 0 if every exemption is still needed, 1 otherwise.

    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    problems = stale_exemptions(pyproject, lock_text, datetime.now(UTC))
    for problem in problems:
        sys.stderr.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
