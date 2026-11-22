"""Tests for the check of repeated contracts."""

import ast
import textwrap
from pathlib import Path

import orjson
import pytest
from scripts import check_abstractions, check_contract_overlap

LAYERS = ["llm", "graphs", "core"]
PYPROJECT = """
[tool.importlinter]
root_package = "pkg"

[[tool.importlinter.contracts]]
type = "layers"
layers = ["pkg.llm", "pkg.graphs", "pkg.core"]
"""

READER = '''
from typing import Protocol

class Reader(Protocol):
    """A reader."""

    def read(self, *, name: str, size: int = 3) -> str:
        """Read."""
        ...
'''
COPY: str = READER.replace("Reader", "Copy").replace("A reader", "A copy of it, with other words")


def method(source: str) -> str:
    [function] = ast.parse(textwrap.dedent(source)).body
    assert isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
    return check_contract_overlap.normalize_method(function)


def make_repo(root: Path, modules: dict[str, str], registry: str = "schema_version: 1\ncapabilities: []\n") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "architecture").mkdir(exist_ok=True)
    (root / "architecture" / "abstractions.yml").write_text(registry, encoding="utf-8")
    for name, content in {"src/pkg/__init__.py": "", **modules}.items():
        path = root / "src" / "pkg" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    return root


def findings(root: Path) -> list[tuple[str, str]]:
    registry, _ = check_abstractions.load_registry(root)
    contracts = check_contract_overlap.find_contracts(root, LAYERS)
    return [
        (item.severity, item.rule_id)
        for item in check_contract_overlap.overlap_diagnostics(contracts, registry, "r.yml")
    ]


def capability(identifier: str, symbol: str, context: str = "production") -> str:
    return (
        f"  - id: {identifier}\n    responsibility: Read {identifier}\n    owner: pkg\n"
        f"    symbol: {symbol}\n    status: active\n    context: {context}\n"
    )


def test_signature_ignores_formatting_docstring_and_body() -> None:
    first = method('def f(self, a: int) -> str:\n    """Doc."""\n    ...')
    second = method("def f(self,\n      a: int,\n      ) -> str:\n    return 'x'")
    assert first == second


@pytest.mark.parametrize(
    "other",
    [
        "def g(self, a: int) -> str: ...",
        "def f(self, b: int) -> str: ...",
        "def f(self, a: float) -> str: ...",
        "def f(self, a: int) -> int: ...",
        "async def f(self, a: int) -> str: ...",
        "def f(self, a: int = 1) -> str: ...",
        "def f(self, *, a: int) -> str: ...",
        "def f(self, a: int, /) -> str: ...",
        "def f(self, a: int, *rest: int) -> str: ...",
        "def f(self, a: int, **rest: int) -> str: ...",
        "@property\ndef f(self, a: int) -> str: ...",
    ],
)
def test_signature_differs_when_the_call_shape_differs(other: str) -> None:
    assert method(other) != method("def f(self, a: int) -> str: ...")


def test_signature_drops_self_but_not_a_parameter_of_a_static_method() -> None:
    assert method("def f(self, a: int): ...") == method("def f(cls, a: int): ...")
    assert method("@staticmethod\ndef f(a: int): ...") != method("def f(a: int): ...")


def test_signature_ignores_abstractmethod_and_overload() -> None:
    plain = method("def f(self, a: int): ...")
    assert method("@abstractmethod\ndef f(self, a: int): ...") == plain
    assert method("@typing.overload\ndef f(self, a: int): ...") == plain


def test_contract_finder_reads_protocol_abc_and_subscript_bases(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "graphs/__init__.py": "",
            "graphs/shapes.py": """
                import abc
                import typing
                from typing import Protocol

                class First(Protocol):
                    def one(self) -> int: ...

                class Second[T](typing.Protocol[T]):
                    def two(self) -> int: ...

                class Third(abc.ABC):
                    @abc.abstractmethod
                    def three(self) -> int: ...

                class _Hidden(Protocol):
                    def four(self) -> int: ...

                class Plain:
                    def five(self) -> int: ...

                class Empty(Protocol):
                    x: int

                class Mixed(Protocol, metaclass=abc.ABCMeta):
                    def _private(self) -> int: ...
                    def __call__(self) -> int: ...

                class Odd(make_base()):
                    def six(self) -> int: ...
            """,
        },
    )
    contracts = check_contract_overlap.find_contracts(root, LAYERS)
    assert [contract.reference for contract in contracts] == [
        "pkg.graphs.shapes:First",
        "pkg.graphs.shapes:Mixed",
        "pkg.graphs.shapes:Second",
        "pkg.graphs.shapes:Third",
    ]
    assert {contract.layer for contract in contracts} == {"graphs"}
    assert contracts[1].names == frozenset()


def test_one_contract_alone_is_fine(tmp_path: Path) -> None:
    assert findings(make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER})) == []


def test_identical_unregistered_contracts_warn(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": COPY})
    assert findings(root) == [("warning", "identical-contract")]


def test_identical_contracts_registered_in_one_context_fail(tmp_path: Path) -> None:
    registry = "schema_version: 1\ncapabilities:\n" + capability("reader", "pkg.graphs.reader:Reader")
    registry += capability("copy", "pkg.graphs.copy:Copy")
    root = make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": COPY}, registry)
    assert findings(root) == [("error", "duplicate-contract")]


def test_identical_contracts_of_two_contexts_only_warn(tmp_path: Path) -> None:
    registry = "schema_version: 1\ncapabilities:\n" + capability("reader", "pkg.graphs.reader:Reader")
    registry += capability("copy", "pkg.graphs.copy:Copy", context="benchmark")
    root = make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": COPY}, registry)
    assert findings(root) == [("warning", "identical-contract")]


def test_consumer_contract_in_a_higher_layer_warns_with_the_inversion_cue(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {"graphs/__init__.py": "", "graphs/reader.py": READER, "llm/__init__.py": "", "llm/copy.py": COPY},
    )
    registry, _ = check_abstractions.load_registry(root)
    contracts = check_contract_overlap.find_contracts(root, LAYERS)
    [finding] = check_contract_overlap.overlap_diagnostics(contracts, registry, "r.yml")
    assert "own Protocol" in finding.suggestion
    assert finding.severity == "warning"


def test_similar_contracts_warn(tmp_path: Path) -> None:
    other = READER.replace("Reader", "Other").replace("size: int = 3", "size: float")
    root = make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/other.py": other})
    assert findings(root) == [("warning", "similar-contract")]


def test_contracts_with_other_method_names_are_not_similar(tmp_path: Path) -> None:
    other = READER.replace("Reader", "Other").replace("def read(", "def write(")
    assert (
        findings(make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/other.py": other}))
        == []
    )


def test_call_protocols_with_different_signatures_are_not_similar(tmp_path: Path) -> None:
    first = "from typing import Protocol\nclass A(Protocol):\n    def __call__(self, x: int) -> int: ...\n"
    second = "from typing import Protocol\nclass B(Protocol):\n    def __call__(self, y: str) -> str: ...\n"
    assert findings(make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/a.py": first, "graphs/b.py": second})) == []


def test_approved_pair_is_skipped_and_a_stale_one_fails(tmp_path: Path) -> None:
    reason = "The consumer keeps its own contract to avoid an upward import."
    registry = (
        "schema_version: 1\ncapabilities: []\nexceptions:\n"
        f"  - symbols: [pkg.graphs.copy:Copy, pkg.graphs.reader:Reader]\n    reason: {reason}\n"
    )
    modules = {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": COPY}
    assert findings(make_repo(tmp_path / "approved", modules, registry)) == []
    changed = COPY.replace("size: int = 3", "other_name: bytes")
    stale = {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": changed.replace("read(", "write(")}
    assert findings(make_repo(tmp_path / "stale", stale, registry)) == [("error", "stale-exception")]


def test_exception_with_a_missing_contract_is_left_to_the_registry_check(tmp_path: Path) -> None:
    registry = (
        "schema_version: 1\ncapabilities: []\nexceptions:\n"
        "  - symbols: [pkg.a:A, pkg.b:B]\n    reason: a reason with enough words\n"
    )
    assert findings(make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER}, registry)) == []


def test_main_exit_code_follows_the_errors_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_repo(tmp_path / "warn", {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": COPY})
    assert check_contract_overlap.main(["--root", str(root)]) == 0
    assert "warning: " in capsys.readouterr().out
    registry = "schema_version: 1\ncapabilities:\n" + capability("reader", "pkg.graphs.reader:Reader")
    registry += capability("copy", "pkg.graphs.copy:Copy")
    failing = make_repo(
        tmp_path / "fail",
        {"graphs/__init__.py": "", "graphs/reader.py": READER, "graphs/copy.py": COPY},
        registry,
    )
    assert check_contract_overlap.main(["--root", str(failing), "--format", "json"]) == 1
    assert orjson.loads(capsys.readouterr().out)[0]["rule_id"] == "duplicate-contract"


def test_main_with_no_overlap_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_repo(tmp_path, {"graphs/__init__.py": "", "graphs/reader.py": READER})
    assert check_contract_overlap.main(["--root", str(root)]) == 0
    assert "no contract repeats another" in capsys.readouterr().out


def test_the_contracts_of_this_repository_have_no_error() -> None:
    assert check_contract_overlap.main([]) == 0
