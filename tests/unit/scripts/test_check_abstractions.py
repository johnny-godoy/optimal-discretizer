"""Tests for the check of the registry of shared abstractions."""

import textwrap
from pathlib import Path

import orjson
import pytest
from scripts import check_abstractions

PYPROJECT = """
[tool.importlinter]
root_package = "pkg"

[[tool.importlinter.contracts]]
type = "layers"
layers = ["pkg.llm", "pkg.graphs", "pkg.core"]
"""

SOURCES = {
    "src/pkg/__init__.py": '"""Package."""\n',
    "src/pkg/core/__init__.py": '"""Core."""\n',
    "src/pkg/graphs/__init__.py": '"""Graphs."""\n',
    "src/pkg/graphs/terms.py": (
        "def main_term(ebm, feature_index):\n    return feature_index\n\n"
        "def _private_helper():\n    return 1\n\n"
        "class TermTable:\n    pass\n\n"
        "LOOKUP = {}\n"
        "Alias: int = 1\n"
        "type TermId = int\n"
    ),
    "src/pkg/llm/__init__.py": '"""LLM."""\n',
    "src/other_package/generated.py": "def generated_entry():\n    return 1\n",
}

VALID = """
schema_version: 1
capabilities:
  - id: term-lookup
    responsibility: Find the term of a feature
    owner: pkg.graphs
    symbol: pkg.graphs.terms:main_term
    consumers: [pkg.llm]
    keywords: [term, feature]
    status: active
exceptions: []
"""


def make_repo(root: Path, registry: str | None = VALID) -> Path:
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    for name, content in SOURCES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if registry is not None:
        path = root / "architecture" / "abstractions.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(registry), encoding="utf-8")
    return root


def rules(root: Path) -> list[str]:
    return [finding.rule_id for finding in check_abstractions.check(root)]


def entry(**changes: str) -> str:
    fields = {
        "id": "term-lookup",
        "responsibility": "Find the term of a feature",
        "owner": "pkg.graphs",
        "symbol": "pkg.graphs.terms:main_term",
        "status": "active",
    }
    fields.update(changes)
    lines = [
        f"  - {key}: {value}" if number == 0 else f"    {key}: {value}"
        for number, (key, value) in enumerate(fields.items())
    ]
    return "\n".join(lines)


def registry_of(*entries: str, exceptions: str = "[]") -> str:
    return "schema_version: 1\ncapabilities:\n" + "\n".join(entries) + f"\nexceptions: {exceptions}\n"


def test_valid_registry_passes(tmp_path: Path) -> None:
    assert rules(make_repo(tmp_path)) == []


def test_private_helper_and_unregistered_class_need_no_entry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    index = check_abstractions.build_index(root)
    assert "pkg.graphs.terms:_private_helper" not in index.symbols
    assert "pkg.graphs.terms:TermTable" in index.symbols
    assert rules(root) == []


def test_index_holds_each_kind_of_public_name_and_skips_the_generated_sdk(tmp_path: Path) -> None:
    index = check_abstractions.build_index(make_repo(tmp_path))
    kinds = {symbol.name: symbol.kind for symbol in index.symbols.values()}
    assert kinds == {
        "main_term": "function",
        "TermTable": "class",
        "LOOKUP": "alias",
        "Alias": "alias",
        "TermId": "alias",
    }
    assert not any(module.startswith("other_package") for module in index.modules)
    assert {"pkg", "pkg.core", "pkg.graphs", "pkg.graphs.terms", "pkg.llm"} == set(index.modules)


def test_missing_symbol_names_the_registry_line_and_a_close_match(tmp_path: Path) -> None:
    root = make_repo(tmp_path, registry_of(entry(symbol="pkg.graphs.terms:main_terms")))
    [finding] = check_abstractions.check(root)
    assert finding.rule_id == "missing-symbol"
    assert (finding.path, finding.line, finding.capability_id) == ("architecture/abstractions.yml", 3, "term-lookup")
    assert "pkg.graphs.terms:main_term" in finding.suggestion


def test_missing_symbol_without_a_close_match_says_to_fix_or_remove(tmp_path: Path) -> None:
    root = make_repo(tmp_path, registry_of(entry(symbol="pkg.graphs.terms:zzz")))
    [finding] = check_abstractions.check(root)
    assert "renamed or deleted" in finding.suggestion


def test_two_entries_with_one_id_fail(tmp_path: Path) -> None:
    other = entry(responsibility="Another job", symbol="pkg.graphs.terms:TermTable")
    root = make_repo(tmp_path, registry_of(entry(), other))
    assert rules(root) == ["duplicate-id"]


def test_two_active_entries_for_one_symbol_fail(tmp_path: Path) -> None:
    other = entry(id="term-table", responsibility="Another job")
    assert rules(make_repo(tmp_path, registry_of(entry(), other))) == ["duplicate-symbol"]


def test_one_responsibility_with_other_punctuation_fails(tmp_path: Path) -> None:
    other = entry(id="term-table", responsibility="find the TERM of a feature!", symbol="pkg.graphs.terms:TermTable")
    assert rules(make_repo(tmp_path, registry_of(entry(), other))) == ["duplicate-responsibility"]


def test_one_responsibility_in_another_context_is_allowed(tmp_path: Path) -> None:
    other = entry(id="term-table", symbol="pkg.graphs.terms:TermTable", context="benchmark")
    assert rules(make_repo(tmp_path, registry_of(entry(), other))) == []


def test_deprecated_entry_may_repeat_a_claim_and_needs_a_replacement(tmp_path: Path) -> None:
    old = entry(id="old-lookup", status="deprecated")
    assert rules(make_repo(tmp_path, registry_of(entry(), old))) == ["missing-replacement"]
    replaced = entry(id="old-lookup", status="deprecated", replaced_by="term-lookup")
    assert rules(make_repo(tmp_path, registry_of(entry(), replaced))) == []
    unknown = entry(id="old-lookup", status="deprecated", replaced_by="no-such-id")
    assert rules(make_repo(tmp_path, registry_of(entry(), unknown))) == ["unknown-replacement"]


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        ({"id": "Term_Lookup"}, "invalid-id"),
        ({"status": "retired"}, "invalid-status"),
        ({"owner": "pkg.nowhere"}, "unknown-owner symbol-owner-mismatch"),
        ({"symbol": "no-colon"}, "invalid-symbol"),
        ({"owner": "pkg.core"}, "symbol-owner-mismatch"),
        ({"consumers": "[pkg.nowhere]"}, "unknown-consumer"),
    ],
)
def test_entry_problems(tmp_path: Path, changes: dict[str, str], rule: str) -> None:
    assert rules(make_repo(tmp_path, registry_of(entry(**changes)))) == rule.split()


def test_owner_may_be_a_package_above_the_module(tmp_path: Path) -> None:
    assert rules(make_repo(tmp_path, registry_of(entry(owner="pkg.graphs.terms")))) == []


@pytest.mark.parametrize(
    ("registry", "message"),
    [
        ("a: [unclosed", "malformed"),
        ("- just a list\n", "must be a mapping"),
        ("schema_version: 2\n", "schema_version"),
        ("schema_version: 1\ncapabilities: nope\n", "must be a list"),
        ("schema_version: 1\ncapabilities:\n  - plain text\n", "must be a mapping"),
        ("schema_version: 1\ncapabilities:\n  - id: only-id\n", "needs a text value for"),
        (registry_of(entry() + "\n    keywords: nope"), "must be lists of text"),
        ("schema_version: 1\nexceptions:\n  - symbols: [a:B]\n    reason: because\n", "two module:Name"),
    ],
)
def test_malformed_registry(tmp_path: Path, registry: str, message: str) -> None:
    [finding] = check_abstractions.check(make_repo(tmp_path, registry))
    assert finding.rule_id == "registry-schema"
    assert message in finding.suggestion


def test_missing_registry_file_fails(tmp_path: Path) -> None:
    [finding] = check_abstractions.check(make_repo(tmp_path, None))
    assert "missing" in finding.suggestion


def test_exception_needs_a_reason_and_existing_symbols(tmp_path: Path) -> None:
    exceptions = "\n  - symbols: [pkg.graphs.terms:TermTable, pkg.graphs.terms:Gone]\n    reason: too short"
    root = make_repo(tmp_path, registry_of(entry(), exceptions=exceptions))
    assert rules(root) == ["exception-reason", "exception-missing-symbol"]


def test_exception_with_a_reason_passes(tmp_path: Path) -> None:
    reason = "The consumer keeps its own contract to avoid an upward import."
    exceptions = f"\n  - symbols: [pkg.graphs.terms:TermTable, pkg.graphs.terms:main_term]\n    reason: {reason}"
    assert rules(make_repo(tmp_path, registry_of(entry(), exceptions=exceptions))) == []


def test_diagnostic_renders_for_a_person(tmp_path: Path) -> None:
    root = make_repo(tmp_path, registry_of(entry(symbol="pkg.graphs.terms:zzz")))
    [finding] = check_abstractions.check(root)
    assert finding.render().startswith(
        "architecture/abstractions.yml:3: missing-symbol [term-lookup] (pkg.graphs.terms:zzz) - ",
    )
    warning = check_abstractions.Diagnostic("rule", "file", 1, "", "", "text", severity="warning")
    assert warning.render() == "warning: file:1: rule - text"


def test_search_ranks_capabilities_before_other_symbols(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    registry, _ = check_abstractions.load_registry(root)
    hits = check_abstractions.search(
        registry,
        check_abstractions.build_index(root),
        ["term", "lookup"],
        ["llm", "graphs", "core"],
    )
    assert hits[0].kind == "capability"
    assert hits[0].score == 2
    assert hits[0].imported_by == "importable from llm, graphs"
    assert all(hit.kind == "symbol" for hit in hits[1:])
    assert [hit.name for hit in hits[1:]] == sorted(hit.name for hit in hits[1:])


def test_search_reads_the_registry_line_when_the_symbol_is_gone(tmp_path: Path) -> None:
    root = make_repo(tmp_path, registry_of(entry(symbol="pkg.graphs.terms:gone")))
    registry, _ = check_abstractions.load_registry(root)
    [hit] = check_abstractions.search(
        registry,
        check_abstractions.build_index(root),
        ["feature"],
        ["llm", "graphs", "core"],
    )
    assert (hit.path, hit.line) == ("architecture/abstractions.yml", 3)


def test_search_cuts_camel_case_names(tmp_path: Path) -> None:
    root = make_repo(tmp_path, None)
    registry, _ = check_abstractions.load_registry(root)
    hits = check_abstractions.search(
        registry,
        check_abstractions.build_index(root),
        ["table"],
        ["llm", "graphs", "core"],
    )
    assert [hit.name for hit in hits] == ["pkg.graphs.terms:TermTable"]


@pytest.mark.parametrize(
    ("owner", "expected"),
    [
        ("pkg.llm.options", "importable from llm"),
        ("pkg.core", "importable from llm, graphs, core"),
        ("pkg.benchmark", "imported by no other layer (it stands alone)"),
        ("pkg", "imported by no other layer (it stands alone)"),
    ],
)
def test_importable_by(owner: str, expected: str) -> None:
    assert check_abstractions.importable_by(owner, ["llm", "graphs", "core"]) == expected


def test_main_check_prints_json_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_repo(tmp_path, registry_of(entry(symbol="pkg.graphs.terms:zzz")))
    assert check_abstractions.main(["--check", "--format", "json", "--root", str(root)]) == 1
    [row] = orjson.loads(capsys.readouterr().out)
    assert set(row) == {"rule_id", "path", "line", "capability_id", "candidate", "suggestion", "severity"}
    assert row["rule_id"] == "missing-symbol"


def test_main_default_checks_and_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_abstractions.main(["--root", str(make_repo(tmp_path))]) == 0
    assert "is right" in capsys.readouterr().out


def test_main_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_abstractions.main(["--list", "--root", str(make_repo(tmp_path))]) == 0
    assert capsys.readouterr().out.startswith("pkg.graphs: term-lookup (active) pkg.graphs.terms:main_term")


def test_main_search_text_and_no_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = str(make_repo(tmp_path))
    assert check_abstractions.main(["--search", "term", "--root", root]) == 0
    assert capsys.readouterr().out.startswith("capability: term-lookup (src/pkg/graphs/terms.py:1)")
    assert check_abstractions.main(["--search", "zzz", "--root", root]) == 0
    assert "no match" in capsys.readouterr().out


def test_main_search_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    check_abstractions.main(["--search", "term", "--format", "json", "--root", str(make_repo(tmp_path))])
    assert orjson.loads(capsys.readouterr().out)[0]["name"] == "term-lookup"


def test_the_registry_of_this_repository_is_right() -> None:
    assert check_abstractions.check(check_abstractions.ROOT) == []
