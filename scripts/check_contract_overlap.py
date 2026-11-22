"""Find contracts of the package in ``src`` that repeat each other.

A contract is a public ``Protocol`` or ``ABC`` class. Two contracts with the same method signatures are a sign that one
of them is a copy. The check reads the source with ``ast``, never imports it, and ignores docstrings, comments, the
order of the methods and the formatting. A signature is the name, the decorators, the parameters with their
annotations, and the return annotation of a method.

Equal signatures do not prove equal meaning, so only a strong case is an error:

- ``duplicate-contract`` (error): two active registered capabilities of the same context have contracts with identical
  signatures. Reuse one contract, or approve the pair with an entry under ``exceptions`` in
  ``architecture/abstractions.yml``.
- ``stale-exception`` (error): an approved pair no longer overlaps. Remove the entry.
- ``identical-contract`` (warning): identical signatures, but the contracts are unregistered, or belong to other
  contexts, or sit in other layers. A consumer may define its own ``Protocol`` to keep the import direction.
- ``similar-contract`` (warning): the contracts share at least half of their method names.

Run it from the repo root: ``uv run python -m scripts.check_contract_overlap``. ``--format json`` prints JSON.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import ast
import itertools
import sys
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

import attrs

from scripts.check_abstractions import (
    ACTIVE,
    ERROR,
    ROOT,
    WARNING,
    Capability,
    Diagnostic,
    OverlapException,
    Registry,
    emit,
    load_registry,
    module_name,
    source_path,
)
from scripts.check_layout import layer_names

CONTRACT_BASES = frozenset({"Protocol", "ABC"})
IGNORED_DECORATORS = frozenset({"abstractmethod", "overload"})
CALL_METHOD = "__call__"
SIMILARITY = 0.5


@attrs.frozen
class Contract:
    """A public ``Protocol`` or ``ABC`` class.

    Parameters
    ----------
    reference: str
        The contract as ``module:Name``.
    path: str
        The file, relative to the repo root.
    line: int
        The line of the class.
    signatures: frozenset[str]
        One normalized text for each method.
    names: frozenset[str]
        The method names, without ``__call__``.
    layer: str
        The layer package, for example ``graphs``.

    """

    reference: str
    path: str
    line: int
    signatures: frozenset[str]
    names: frozenset[str]
    layer: str


def _base_name(base: ast.expr) -> str:
    """Read the last name of a base class expression.

    Parameters
    ----------
    base: ast.expr
        A base of a class, such as ``Protocol``, ``abc.ABC`` or ``Protocol[T]``.

    Returns
    -------
    str
        The last name, or an empty string for any other expression.

    """
    if isinstance(base, ast.Subscript):
        return _base_name(base.value)
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Name):
        return base.id
    return ""


def _decorator_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """List the decorators that change the call shape of a method.

    Parameters
    ----------
    function: ast.FunctionDef | ast.AsyncFunctionDef
        The method.

    Returns
    -------
    list[str]
        The sorted names. ``abstractmethod`` and ``overload`` are left out, because they do not change the call shape.

    """
    names = {_base_name(decorator) for decorator in function.decorator_list}
    return sorted(name for name in names if name and name not in IGNORED_DECORATORS)


def _annotation(argument: ast.arg) -> str:
    """Dump the annotation of a parameter, so that the formatting does not matter.

    Parameters
    ----------
    argument: ast.arg
        The parameter.

    Returns
    -------
    str
        The dump, or an empty string if the parameter has no annotation.

    """
    return ast.dump(argument.annotation) if argument.annotation else ""


def _parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Normalize the parameters of a method.

    Parameters
    ----------
    function: ast.FunctionDef | ast.AsyncFunctionDef
        The method.

    Returns
    -------
    list[str]
        One text for each parameter: its kind, name, annotation and whether it has a default. The first parameter of a
        method that is not static (``self`` or ``cls``) is left out.

    """
    arguments = function.args
    positional = [("positional-only", argument) for argument in arguments.posonlyargs]
    positional += [("positional", argument) for argument in arguments.args]
    if "staticmethod" not in _decorator_names(function):
        positional = positional[1:]
    defaults = len(arguments.defaults)
    parts = [(kind, argument, index >= len(positional) - defaults) for index, (kind, argument) in enumerate(positional)]
    parts += [
        ("keyword-only", argument, default is not None)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
    ]
    if arguments.vararg:
        parts.append(("variadic", arguments.vararg, False))
    if arguments.kwarg:
        parts.append(("variadic-keyword", arguments.kwarg, False))
    return [
        f"{kind} {argument.arg}: {_annotation(argument)}{' =' if has_default else ''}"
        for kind, argument, has_default in parts
    ]


def normalize_method(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reduce a method to a text that ignores the formatting, the docstring and the body.

    Parameters
    ----------
    function: ast.FunctionDef | ast.AsyncFunctionDef
        The method.

    Returns
    -------
    str
        The text that holds the name, ``async``, the decorators, the parameters and the return annotation.

    """
    returns = ast.dump(function.returns) if function.returns else ""
    asynchronous = "async " if isinstance(function, ast.AsyncFunctionDef) else ""
    decorators = ",".join(_decorator_names(function))
    return f"{asynchronous}{function.name}[{decorators}]({'; '.join(_parameters(function))}) -> {returns}"


def _contracts_of(tree: ast.Module, module: str, path: str, layer: str) -> Iterable[Contract]:
    """List the public contracts that a module defines.

    Parameters
    ----------
    tree: ast.Module
        The parsed module.
    module: str
        The dotted name of the module.
    path: str
        The file, relative to the repo root.
    layer: str
        The layer package of the module.

    Yields
    ------
    Contract
        Each top-level class with a ``Protocol`` or ``ABC`` base, a public name, and at least one public method.

    """
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
            continue
        if not CONTRACT_BASES & {_base_name(base) for base in node.bases}:
            continue
        methods = [
            item
            for item in node.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            and (not item.name.startswith("_") or item.name == CALL_METHOD)
        ]
        if methods:
            yield Contract(
                reference=f"{module}:{node.name}",
                path=path,
                line=node.lineno,
                signatures=frozenset(normalize_method(method) for method in methods),
                names=frozenset(method.name for method in methods if method.name != CALL_METHOD),
                layer=layer,
            )


def find_contracts(root: Path, layers: Sequence[str]) -> list[Contract]:
    """Find every public contract of the package in ``src``.

    Parameters
    ----------
    root: Path
        The repo root.
    layers: Sequence[str]
        The layer package names.

    Returns
    -------
    list[Contract]
        The contracts, sorted by reference.

    """
    contracts: list[Contract] = []
    for source in sorted((root / source_path(root)).rglob("*.py")):
        module = module_name(source, root)
        parts = module.split(".")
        layer = parts[1] if len(parts) > 1 and parts[1] in layers else ""
        contracts.extend(
            _contracts_of(ast.parse(source.read_bytes()), module, source.relative_to(root).as_posix(), layer),
        )
    return sorted(contracts, key=lambda contract: contract.reference)


def _is_similar(first: Contract, second: Contract) -> bool:
    """Tell whether two contracts share at least half of their method names.

    Parameters
    ----------
    first: Contract
        One contract.
    second: Contract
        The other contract.

    Returns
    -------
    bool
        True if the shared names are at least ``SIMILARITY`` of all names of the two contracts.

    """
    union = first.names | second.names
    return bool(union) and len(first.names & second.names) / len(union) >= SIMILARITY


def _pair_finding(first: Contract, second: Contract, registered: dict[str, Capability]) -> Diagnostic | None:
    """Judge one pair of contracts.

    Parameters
    ----------
    first: Contract
        The contract that comes first by reference.
    second: Contract
        The other contract.
    registered: dict[str, Capability]
        The active capabilities by symbol.

    Returns
    -------
    Diagnostic | None
        The finding about the pair, or ``None`` if the contracts differ.

    """
    pair = f"{first.reference} + {second.reference}"
    identical = first.signatures == second.signatures
    if not identical and not _is_similar(first, second):
        return None
    if not identical:
        return Diagnostic(
            "similar-contract",
            second.path,
            second.line,
            "",
            first.reference,
            f"check whether {pair} should share one contract",
            severity=WARNING,
        )
    one, other = registered.get(first.reference), registered.get(second.reference)
    if one and other and one.context == other.context:
        return Diagnostic(
            "duplicate-contract",
            second.path,
            second.line,
            other.capability_id,
            first.reference,
            f"reuse {one.capability_id}, or approve the pair under `exceptions` in architecture/abstractions.yml",
        )
    note = (
        "a consumer may define its own Protocol to keep the import direction"
        if first.layer != second.layer
        else "register the contracts or merge them"
    )
    return Diagnostic(
        "identical-contract",
        second.path,
        second.line,
        "",
        first.reference,
        f"{pair} have identical signatures: {note}",
        severity=WARNING,
    )


def _is_approved(exception: OverlapException, first: Contract, second: Contract) -> bool:
    """Tell whether an exception covers a pair of contracts.

    Parameters
    ----------
    exception: OverlapException
        The exception.
    first: Contract
        One contract.
    second: Contract
        The other contract.

    Returns
    -------
    bool
        True if the exception names exactly these two contracts, in any order.

    """
    return set(exception.symbols) == {first.reference, second.reference}


def overlap_diagnostics(contracts: Sequence[Contract], registry: Registry, path: str) -> list[Diagnostic]:
    """Compare every pair of contracts.

    Parameters
    ----------
    contracts: Sequence[Contract]
        The contracts of the source.
    registry: Registry
        The parsed registry, for the capabilities and the approved pairs.
    path: str
        The registry file, for the findings about its exceptions.

    Returns
    -------
    list[Diagnostic]
        The findings. Errors fail the check, and warnings are review cues.

    """
    registered = {item.symbol: item for item in registry.capabilities if item.status == ACTIVE}
    by_reference = {contract.reference: contract for contract in contracts}
    found: list[Diagnostic] = []
    overlapping: set[frozenset[str]] = set()
    for first, second in itertools.combinations(contracts, 2):
        finding = _pair_finding(first, second, registered)
        if finding is None:
            continue
        overlapping.add(frozenset({first.reference, second.reference}))
        if not any(_is_approved(exception, first, second) for exception in registry.exceptions):
            found.append(finding)
    found.extend(
        Diagnostic(
            "stale-exception",
            path,
            exception.line,
            "",
            " + ".join(exception.symbols),
            "the contracts no longer overlap: remove the exception",
        )
        for exception in registry.exceptions
        if set(exception.symbols) <= by_reference.keys() and frozenset(exception.symbols) not in overlapping
    )
    return found


def run(*, output_format: Literal["text", "json"] = "text", root: Path = ROOT) -> int:
    """Check the registered contracts for identical signatures.

    Parameters
    ----------
    output_format: Literal["text", "json"]
        The output format.
    root: Path
        The repo root. The default is this repository.

    Returns
    -------
    int
        The process exit code: 1 if the check found an error, else 0. A warning does not fail the check.

    """
    layers = layer_names(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")))
    registry, shape_problems = load_registry(root)
    findings = shape_problems + overlap_diagnostics(
        find_contracts(root, layers),
        registry,
        "architecture/abstractions.yml",
    )
    emit(findings, output_format, "no contract repeats another")
    return 1 if any(finding.severity == ERROR for finding in findings) else 0


def main(argv: Sequence[str] = ()) -> int:
    """Run the command line.

    Parameters
    ----------
    argv: Sequence[str]
        The arguments. The default is none, which checks this repository.

    Returns
    -------
    int
        The process exit code: 1 if the check found an error, else 0. A warning does not fail the check.

    """
    parser = argparse.ArgumentParser(prog="check_contract_overlap", description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=["text", "json"], default="text", dest="output_format")
    parser.add_argument("--root", type=Path, default=ROOT, help="the repo root")
    arguments = parser.parse_args(list(argv))
    return run(output_format=arguments.output_format, root=arguments.root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
