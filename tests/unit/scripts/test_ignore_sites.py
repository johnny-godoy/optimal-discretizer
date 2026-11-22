"""Tests for the workaround finder, its checker and the audit report."""

from pathlib import Path

import pytest
from scripts import check_ignores, compile_ignores, ignore_sites
from scripts.ignore_sites import Site


def test_comment_reason_follows_the_double_dash() -> None:
    sites = ignore_sites.comment_sites("x.py", {3: "# noqa: S603 -- fixed argv, never untrusted input"})
    assert sites == [Site("ruff", "x.py", 3, "noqa: S603", "fixed argv, never untrusted input")]


def test_comment_without_reason_has_an_empty_one() -> None:
    (site,) = ignore_sites.comment_sites("x.py", {1: "# type: ignore[arg-type]"})
    assert (site.program, site.reason, site.reason_problem) == ("pyrefly", "", "has no reason")


def test_plain_comments_are_not_workarounds() -> None:
    assert ignore_sites.comment_sites("x.py", {1: "# nothing to see -- here"}) == []


def test_strings_that_look_like_ignores_are_not_workarounds() -> None:
    source = 'x = "# noqa"\n'
    assert ignore_sites.pytest_sites("x.py", source, ignore_sites._comments(source)) == []
    assert ignore_sites._comments(source) == {}


def test_untokenizable_source_has_no_comments() -> None:
    assert ignore_sites._comments("x = (\n") == {}


def test_pytest_reason_keyword_or_comment() -> None:
    source = (
        "import pytest\n"
        '@pytest.mark.skip(reason="needs the live payment API")\n'
        "def a(): ...\n"
        "@pytest.mark.xfail  # -- upstream bug, fixed in the next interpret release\n"
        "def b(): ...\n"
        "def c():\n"
        "    pytest.skip()\n"
    )
    sites = ignore_sites.pytest_sites("t.py", source, ignore_sites._comments(source))
    assert [(s.what, s.line, s.reason) for s in sites] == [
        ("pytest.mark.skip", 2, "needs the live payment API"),
        ("pytest.mark.xfail", 4, "upstream bug, fixed in the next interpret release"),
        ("pytest.skip", 7, ""),
    ]


def test_pytest_syntax_error_has_no_sites() -> None:
    assert ignore_sites.pytest_sites("t.py", "def (", {}) == []


TOML = """\
[tool.vulture]
# reason: pytest reads pytestmark by name, so vulture
# thinks it is unused.
ignore_names = ["pytestmark"]
exclude = ["x"]

[tool.ruff.lint.per-file-ignores]
# an ordinary comment is not a reason
"a.py" = ["assert"]
"""


def test_toml_reason_block_sits_above_the_key() -> None:
    sites = ignore_sites.config_sites("pyproject.toml", TOML)
    assert [(s.what, s.line, s.reason) for s in sites] == [
        ("tool.ruff.lint.per-file-ignores.a.py", 9, ""),
        ("tool.vulture.ignore_names", 4, "pytest reads pytestmark by name, so vulture thinks it is unused."),
        ("tool.vulture.exclude", 5, ""),
    ]


def test_invalid_toml_has_no_sites() -> None:
    assert ignore_sites.config_sites("pyproject.toml", "= nope") == []


def test_thin_reasons_are_a_problem() -> None:
    assert Site("ruff", "x.py", 1, "noqa", "because").reason_problem is not None
    assert Site("ruff", "x.py", 1, "noqa", "the stub lacks this overload entirely").reason_problem is None


def test_repo_workarounds_all_have_reasons() -> None:
    assert check_ignores.main() == 0


def test_check_reports_every_missing_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(check_ignores, "find_sites", lambda: [Site("ruff", "x.py", 4, "noqa: E501", "")])
    assert check_ignores.main() == 1
    assert "x.py:4 (ruff): has no reason" in capsys.readouterr().err


def test_report_groups_by_tool_and_flags_missing_reasons() -> None:
    sites = [
        Site("ruff", "a.py", 1, "noqa: E501", "an upstream URL that cannot wrap"),
        Site("ruff", "a.py", 2, "noqa: A001", ""),
        Site("vulture", "pyproject.toml", 3, "x | y", "vulture cannot see injection"),
    ]
    report = compile_ignores.render(sites)
    assert "3 workaround(s), 1 without a proper reason." in report
    assert "## ruff" in report
    assert "| `a.py:2` | `noqa: A001` | **MISSING** |" in report
    assert "`x \\| y`" in report


def test_empty_report_has_no_tables() -> None:
    assert compile_ignores.render([]) == "# Workaround audit\n\n0 workaround(s), 0 without a proper reason.\n"


def test_main_writes_the_report_to_a_file(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    assert compile_ignores.main(["-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8").startswith("# Workaround audit")


def test_main_prints_the_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert compile_ignores.main([]) == 0
    assert capsys.readouterr().out.startswith("# Workaround audit")
