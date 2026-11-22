"""Check the registry of shared abstractions against the source, and search it.

``architecture/abstractions.yml`` lists the shared capabilities of the package in ``src``: the contracts and entry
points that more than one module uses. Each capability has one stable ID, one owner and one canonical symbol. An agent
that wants a new shared contract searches the registry first, so that it reuses an existing one
(``.claude/rules/reuse.md``).

The check reads the source with ``ast`` and never imports it. It fails when:

- the registry is malformed, or an ID is not lower-case kebab-case or is not unique,
- an owner or a consumer is not a module of the package in ``src``,
- a symbol does not exist, or its module is outside the owner,
- two active capabilities claim the same symbol, or the same responsibility in the same owner and context,
- a deprecated capability does not name its replacement,
- an exception for a contract overlap has no reason or names a symbol that does not exist.

A private helper needs no entry. The check fails on no class only because the registry lacks it.

Run it from the repo root:

- ``uv run python -m scripts.check_abstractions --check`` validates the registry (the default).
- ``uv run python -m scripts.check_abstractions --list`` prints the capabilities.
- ``uv run python -m scripts.check_abstractions --search graph text`` finds capabilities and symbols by word.

``--format json`` prints the diagnostics or the hits as JSON. ``--search`` is a lexical search. A search without a hit
does not prove that no equivalent exists, so read the owner modules too.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import ast
import difflib
import re
import sys
import tomllib
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import attrs
import orjson
import yaml

from scripts.check_layout import layer_names

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = Path("architecture") / "abstractions.yml"
SCHEMA_VERSION = 1
ERROR = "error"
WARNING = "warning"
ACTIVE = "active"
DEPRECATED = "deprecated"
STATUSES = (ACTIVE, DEPRECATED)
DEFAULT_CONTEXT = "production"
ID_PATTERN: re.Pattern[str] = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MIN_REASON_WORDS = 4
MIN_REASON_CHARACTERS = 20
CLOSE_MATCH_COUNT = 3


@attrs.frozen
class Diagnostic:
    """One finding of a check, in a form that a person and a tool can read.

    Parameters
    ----------
    rule_id: str
        The stable name of the rule that failed.
    path: str
        The file of the finding, relative to the repo root.
    line: int
        The line of the finding, starting at 1.
    capability_id: str
        The ID of the capability, or an empty string if the finding has none.
    candidate: str
        The existing symbol or capability that the finding refers to, or an empty string.
    suggestion: str
        What to do to fix the finding.
    severity: str
        ``error`` fails the check. ``warning`` is a review cue.

    """

    rule_id: str
    path: str
    line: int
    capability_id: str
    candidate: str
    suggestion: str
    severity: str = ERROR

    def render(self) -> str:
        """Format the finding as one text line.

        Returns
        -------
        str
            ``path:line: rule_id [capability_id] (candidate) - suggestion``. A warning starts with ``warning:``.

        """
        parts = [f"{self.path}:{self.line}: {self.rule_id}"]
        if self.severity != ERROR:
            parts.insert(0, f"{self.severity}:")
        if self.capability_id:
            parts.append(f"[{self.capability_id}]")
        if self.candidate:
            parts.append(f"({self.candidate})")
        return f"{' '.join(parts)} - {self.suggestion}"


@attrs.frozen
class Capability:
    """One entry of the registry.

    Parameters
    ----------
    capability_id: str
        The stable ID in lower-case kebab-case.
    responsibility: str
        One sentence that says what the capability does.
    owner: str
        The module or package that owns the capability, for example ``package.domain``.
    symbol: str
        The canonical symbol as ``module:Name``.
    consumers: tuple[str, ...]
        The modules that use the capability. The list describes, and it grants no import right.
    keywords: tuple[str, ...]
        Words for the search.
    status: str
        ``active`` or ``deprecated``.
    context: str
        The bounded context, ``production`` unless the entry says otherwise.
    replaced_by: str
        The ID of the replacement of a deprecated capability, or an empty string.
    line: int
        The line of the entry in the registry file.

    """

    capability_id: str
    responsibility: str
    owner: str
    symbol: str
    consumers: tuple[str, ...]
    keywords: tuple[str, ...]
    status: str
    context: str
    replaced_by: str
    line: int


@attrs.frozen
class OverlapException:
    """An approved overlap of two contracts, with the reason.

    Parameters
    ----------
    symbols: tuple[str, str]
        The two contracts as ``module:Name``, in any order.
    reason: str
        Why the two contracts stay apart.
    line: int
        The line of the entry in the registry file.

    """

    symbols: tuple[str, str]
    reason: str
    line: int


@attrs.frozen
class Registry:
    """The parsed registry.

    Parameters
    ----------
    capabilities: tuple[Capability, ...]
        The entries, in file order.
    exceptions: tuple[OverlapException, ...]
        The approved contract overlaps.

    """

    capabilities: tuple[Capability, ...]
    exceptions: tuple[OverlapException, ...]


@attrs.frozen
class Symbol:
    """A public top-level name of a module of the package in ``src``.

    Parameters
    ----------
    module: str
        The dotted module, for example ``package.domain.summary``.
    name: str
        The name in the module.
    path: str
        The file, relative to the repo root.
    line: int
        The line of the definition.
    kind: str
        ``class``, ``function`` or ``alias``.

    """

    module: str
    name: str
    path: str
    line: int
    kind: str

    @property
    def reference(self) -> str:
        """Give the symbol as ``module:Name``.

        Returns
        -------
        str
            The reference as the registry writes it.

        """
        return f"{self.module}:{self.name}"


@attrs.frozen
class SourceIndex:
    """The modules and the public symbols of the package in ``src``.

    Parameters
    ----------
    modules: frozenset[str]
        Every module and package, as a dotted name.
    symbols: dict[str, Symbol]
        The public symbols by ``module:Name``.

    """

    modules: frozenset[str]
    symbols: dict[str, Symbol]


@attrs.frozen
class SearchHit:
    """One result of ``--search``.

    Parameters
    ----------
    kind: str
        ``capability`` for a registered entry and ``symbol`` for another public symbol.
    name: str
        The ID of the capability, or the ``module:Name`` of the symbol.
    owner: str
        The owner of the capability, or the module of the symbol.
    path: str
        The file of the canonical symbol.
    line: int
        The line of the definition.
    score: int
        The number of query words that matched.
    imported_by: str
        The layers that may import the hit.

    """

    kind: str
    name: str
    owner: str
    path: str
    line: int
    score: int
    imported_by: str

    def render(self) -> str:
        """Format the hit as one text line.

        Returns
        -------
        str
            The kind, the name, the place, and the layers that may import it.

        """
        return f"{self.kind}: {self.name} ({self.path}:{self.line}) owner {self.owner}; {self.imported_by}"


def source_path(root: Path) -> Path:
    """Find the package that the checks scan.

    Parameters
    ----------
    root: Path
        The repo root.

    Returns
    -------
    Path
        The path of the package relative to the root: ``src`` and the ``root_package`` of ``[tool.importlinter]``.

    """
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package: str = pyproject["tool"]["importlinter"]["root_package"]
    return Path("src") / package


def module_name(source: Path, root: Path) -> str:
    """Turn a source path into a dotted module name.

    Parameters
    ----------
    source: Path
        A Python file under ``root / src``.
    root: Path
        The repo root.

    Returns
    -------
    str
        The dotted name. A package ``__init__.py`` gives the name of the package.

    """
    parts = list(source.relative_to(root / "src").with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _top_level_symbols(tree: ast.Module, module: str, path: str) -> Iterable[Symbol]:
    """List the public top-level names that a module defines.

    Parameters
    ----------
    tree: ast.Module
        The parsed module.
    module: str
        The dotted name of the module.
    path: str
        The file, relative to the repo root.

    Yields
    ------
    Symbol
        A class, a function or a module-level alias whose name has no leading underscore.

    """
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            found = [(node.name, "class")]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found = [(node.name, "function")]
        elif isinstance(node, ast.Assign):
            found = [(target.id, "alias") for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found = [(node.target.id, "alias")]
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            found = [(node.name.id, "alias")]
        else:
            continue
        for name, kind in found:
            if not name.startswith("_"):
                yield Symbol(module=module, name=name, path=path, line=node.lineno, kind=kind)


def build_index(root: Path) -> SourceIndex:
    """Index the modules and the public symbols of the package in ``src`` without importing them.

    Parameters
    ----------
    root: Path
        The repo root.

    Returns
    -------
    SourceIndex
        The modules and symbols.

    """
    modules: set[str] = set()
    symbols: dict[str, Symbol] = {}
    for source in sorted((root / source_path(root)).rglob("*.py")):
        module = module_name(source, root)
        modules.add(module)
        path = source.relative_to(root).as_posix()
        for symbol in _top_level_symbols(ast.parse(source.read_bytes()), module, path):
            symbols[symbol.reference] = symbol
    return SourceIndex(modules=frozenset(modules), symbols=symbols)


def _text_list(value: Any) -> list[str] | None:  # ruff: ignore[any-type] -- the value comes from untyped YAML
    """Read a list of strings from a YAML value.

    Parameters
    ----------
    value: Any
        The parsed YAML value. ``None`` stands for an absent key.

    Returns
    -------
    list[str] | None
        The strings, an empty list for ``None``, or ``None`` if the value is not a list of strings.

    """
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) for item in cast("list[object]", value)):
        return cast("list[str]", list(value))
    return None


def _entry_lines(document: yaml.Node | None, key: str) -> list[int]:
    """Find the line of each item under a top-level key of the registry.

    Parameters
    ----------
    document: yaml.Node | None
        The composed YAML document.
    key: str
        The top-level key whose value is a list.

    Returns
    -------
    list[int]
        The first line of each item, starting at 1. The list is empty if the key is absent.

    """
    if not isinstance(document, yaml.MappingNode):
        return []
    for key_node, value_node in document.value:
        if key_node.value == key and isinstance(value_node, yaml.SequenceNode):
            return [item.start_mark.line + 1 for item in value_node.value]
    return []


def _capability(entry: Mapping[str, Any], line: int) -> Capability | str:
    """Build a capability from one registry entry.

    Parameters
    ----------
    entry: Mapping[str, Any]
        The parsed YAML mapping.
    line: int
        The line of the entry.

    Returns
    -------
    Capability | str
        The capability, or the message that says what is wrong with the entry.

    """
    required = ("id", "responsibility", "owner", "symbol", "status")
    missing = [key for key in required if not isinstance(entry.get(key), str) or not entry[key].strip()]
    consumers = _text_list(entry.get("consumers"))
    keywords = _text_list(entry.get("keywords"))
    if missing:
        return f"the entry needs a text value for {', '.join(missing)}"
    if consumers is None or keywords is None:
        return "consumers and keywords must be lists of text"
    return Capability(
        capability_id=entry["id"],
        responsibility=entry["responsibility"],
        owner=entry["owner"],
        symbol=entry["symbol"],
        consumers=tuple(consumers),
        keywords=tuple(keywords),
        status=entry["status"],
        context=str(entry.get("context", DEFAULT_CONTEXT)),
        replaced_by=str(entry.get("replaced_by", "")),
        line=line,
    )


def _overlap_exception(entry: Mapping[str, Any], line: int) -> OverlapException | str:
    """Build an overlap exception from one registry entry.

    Parameters
    ----------
    entry: Mapping[str, Any]
        The parsed YAML mapping.
    line: int
        The line of the entry.

    Returns
    -------
    OverlapException | str
        The exception, or the message that says what is wrong with the entry.

    """
    symbols = _text_list(entry.get("symbols"))
    reason = entry.get("reason")
    if symbols is None or len(symbols) != 2 or not isinstance(reason, str):  # ruff: ignore[magic-value-comparison] -- an exception names a pair of contracts
        return "an exception needs `symbols` (two module:Name values) and a `reason`"
    return OverlapException(symbols=(symbols[0], symbols[1]), reason=reason, line=line)


def _schema_problem(path: str, line: int, message: str) -> Diagnostic:
    """Build the diagnostic for a malformed registry.

    Parameters
    ----------
    path: str
        The registry file.
    line: int
        The line of the problem.
    message: str
        What is wrong.

    Returns
    -------
    Diagnostic
        A ``registry-schema`` finding.

    """
    return Diagnostic("registry-schema", path, line, "", "", message)


def parse_registry(text: str, path: str = REGISTRY_PATH.as_posix()) -> tuple[Registry, list[Diagnostic]]:
    """Parse the registry text and check its shape.

    Parameters
    ----------
    text: str
        The content of ``architecture/abstractions.yml``.
    path: str
        The file name for the diagnostics.

    Returns
    -------
    tuple[Registry, list[Diagnostic]]
        The valid entries and the findings about the others. A malformed file gives an empty registry.

    """
    empty = Registry(capabilities=(), exceptions=())
    try:
        document: yaml.Node | None = yaml.compose(text)
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return empty, [_schema_problem(path, 1, f"the YAML is malformed: {error}")]
    if not isinstance(data, dict):
        return empty, [_schema_problem(path, 1, "the file must be a mapping with `schema_version` and `capabilities`")]
    if data.get("schema_version") != SCHEMA_VERSION:
        return empty, [_schema_problem(path, 1, f"`schema_version` must be {SCHEMA_VERSION}")]
    capabilities, capability_problems = _parse_items(data, document, "capabilities", _capability, path)
    exceptions, exception_problems = _parse_items(data, document, "exceptions", _overlap_exception, path)
    problems = capability_problems + exception_problems
    return Registry(capabilities=tuple(capabilities), exceptions=tuple(exceptions)), problems


def _parse_items[T](
    data: Mapping[str, Any],
    document: yaml.Node | None,
    key: str,
    build: Callable[[Mapping[str, Any], int], T | str],
    path: str,
) -> tuple[list[T], list[Diagnostic]]:
    """Build the entries under one top-level key of the registry.

    Parameters
    ----------
    data: Mapping[str, Any]
        The parsed registry.
    document: yaml.Node | None
        The composed registry, for the line numbers.
    key: str
        The top-level key, ``capabilities`` or ``exceptions``.
    build: Callable[[Mapping[str, Any], int], T | str]
        Builds one entry from its mapping and its line. It returns a message if the entry is wrong.
    path: str
        The registry file for the diagnostics.

    Returns
    -------
    tuple[list[T], list[Diagnostic]]
        The valid entries and the findings about the others.

    """
    items = data.get(key) or []
    if not isinstance(items, list):
        return [], [_schema_problem(path, 1, f"`{key}` must be a list")]
    lines = _entry_lines(document, key)
    built: list[T] = []
    problems: list[Diagnostic] = []
    for number, item in enumerate(cast("list[object]", items)):
        line = lines[number] if number < len(lines) else 1
        result = build(item, line) if isinstance(item, dict) else "the entry must be a mapping"
        if isinstance(result, str):
            problems.append(_schema_problem(path, line, result))
        else:
            built.append(result)
    return built, problems


def normalize_responsibility(responsibility: str) -> str:
    """Reduce a responsibility to lower-case words, so that a copy with other punctuation matches.

    The reduction is syntactic. It does not prove that two sentences mean the same.

    Parameters
    ----------
    responsibility: str
        The sentence of the entry.

    Returns
    -------
    str
        The words in lower case, separated by single spaces.

    """
    words: list[str] = re.findall(r"[a-z0-9]+", responsibility.lower())
    return " ".join(words)


def _close_names(index: SourceIndex, module: str, name: str) -> str:
    """Name the public symbols of a module that look like a missing one.

    Parameters
    ----------
    index: SourceIndex
        The source index.
    module: str
        The module of the missing symbol.
    name: str
        The missing name.

    Returns
    -------
    str
        Up to three close ``module:Name`` values, comma-separated, or an empty string.

    """
    names = [symbol.name for symbol in index.symbols.values() if symbol.module == module]
    return ", ".join(f"{module}:{close}" for close in difflib.get_close_matches(name, names, n=CLOSE_MATCH_COUNT))


def _inside(module: str, owner: str) -> bool:
    """Tell whether a module is the owner or lies below it.

    Parameters
    ----------
    module: str
        The dotted module.
    owner: str
        The dotted owner.

    Returns
    -------
    bool
        True if ``module`` equals ``owner`` or starts with ``owner.``.

    """
    return module == owner or module.startswith(f"{owner}.")


def _capability_problems(capability: Capability, index: SourceIndex, path: str) -> list[Diagnostic]:
    """Check one capability against the source, without looking at the other capabilities.

    Parameters
    ----------
    capability: Capability
        The entry.
    index: SourceIndex
        The source index.
    path: str
        The registry file.

    Returns
    -------
    list[Diagnostic]
        The findings. The list is empty if the entry is right.

    """
    identity = capability.capability_id
    found: list[Diagnostic] = []
    if not ID_PATTERN.fullmatch(identity):
        found.append(
            Diagnostic("invalid-id", path, capability.line, identity, "", "write the ID in lower-case kebab-case"),
        )
    if capability.status not in STATUSES:
        found.append(
            Diagnostic("invalid-status", path, capability.line, identity, capability.status, f"use one of {STATUSES}"),
        )
    if capability.owner not in index.modules:
        found.append(
            Diagnostic(
                "unknown-owner",
                path,
                capability.line,
                identity,
                capability.owner,
                "name a module or package of the package in src",
            ),
        )
    found.extend(
        Diagnostic(
            "unknown-consumer",
            path,
            capability.line,
            identity,
            consumer,
            "name a module or package of the package in src",
        )
        for consumer in capability.consumers
        if consumer not in index.modules
    )
    module, _, name = capability.symbol.partition(":")
    if not name:
        found.append(
            Diagnostic(
                "invalid-symbol",
                path,
                capability.line,
                identity,
                capability.symbol,
                "write the symbol as module:Name",
            ),
        )
    elif capability.symbol not in index.symbols:
        close = _close_names(index, module, name)
        hint = f"did you mean {close}?" if close else "the symbol was renamed or deleted: fix or remove the entry"
        found.append(Diagnostic("missing-symbol", path, capability.line, identity, capability.symbol, hint))
    elif not _inside(module, capability.owner):
        found.append(
            Diagnostic(
                "symbol-owner-mismatch",
                path,
                capability.line,
                identity,
                module,
                f"move the symbol into {capability.owner} or change the owner",
            ),
        )
    if capability.status == DEPRECATED and not capability.replaced_by:
        found.append(
            Diagnostic(
                "missing-replacement",
                path,
                capability.line,
                identity,
                "",
                "add `replaced_by` with the ID of the replacement",
            ),
        )
    return found


def _first_claim[K](seen: dict[K, Capability], key: K, capability: Capability) -> Capability | None:
    """Record a claim, and return the earlier entry that made the same claim.

    Parameters
    ----------
    seen: dict[K, Capability]
        The first entry for each key.
    key: K
        What the capability claims.
    capability: Capability
        The entry that makes the claim.

    Returns
    -------
    Capability | None
        The earlier entry, or ``None`` if this entry is the first.

    """
    first = seen.setdefault(key, capability)
    return None if first is capability else first


def _collision_problems(capabilities: Sequence[Capability], path: str) -> list[Diagnostic]:
    """Find the claims that two entries make on the same thing.

    Parameters
    ----------
    capabilities: Sequence[Capability]
        Every entry of the registry.
    path: str
        The registry file.

    Returns
    -------
    list[Diagnostic]
        One finding for each later entry that repeats an ID, a symbol or a responsibility, and for each unknown
        replacement.

    """
    found: list[Diagnostic] = []
    by_id: dict[str, Capability] = {}
    by_symbol: dict[str, Capability] = {}
    by_duty: dict[tuple[str, str, str], Capability] = {}
    for capability in capabilities:
        identity = capability.capability_id
        if identity in by_id:
            found.append(
                Diagnostic(
                    "duplicate-id",
                    path,
                    capability.line,
                    identity,
                    f"{path}:{by_id[identity].line}",
                    "keep one entry for the ID",
                ),
            )
        by_id.setdefault(identity, capability)
        if capability.status != ACTIVE:
            continue
        duty = (capability.owner, normalize_responsibility(capability.responsibility), capability.context)
        for rule, earlier in (
            ("duplicate-symbol", _first_claim(by_symbol, capability.symbol, capability)),
            ("duplicate-responsibility", _first_claim(by_duty, duty, capability)),
        ):
            if earlier:
                found.append(
                    Diagnostic(
                        rule,
                        path,
                        capability.line,
                        identity,
                        earlier.capability_id,
                        f"reuse {earlier.capability_id} or mark one entry deprecated",
                    ),
                )
    found.extend(
        Diagnostic(
            "unknown-replacement",
            path,
            capability.line,
            capability.capability_id,
            capability.replaced_by,
            "name an existing ID",
        )
        for capability in capabilities
        if capability.replaced_by and capability.replaced_by not in by_id
    )
    return found


def _exception_problems(exceptions: Sequence[OverlapException], index: SourceIndex, path: str) -> list[Diagnostic]:
    """Check the approved overlaps.

    Parameters
    ----------
    exceptions: Sequence[OverlapException]
        The exceptions of the registry.
    index: SourceIndex
        The source index.
    path: str
        The registry file.

    Returns
    -------
    list[Diagnostic]
        A finding for each exception with a short reason or with a symbol that does not exist.

    """
    found: list[Diagnostic] = []
    for exception in exceptions:
        words = exception.reason.split()
        if len(words) < MIN_REASON_WORDS or len(exception.reason.strip()) < MIN_REASON_CHARACTERS:
            found.append(
                Diagnostic(
                    "exception-reason",
                    path,
                    exception.line,
                    "",
                    " + ".join(exception.symbols),
                    "say why the contracts stay apart, in at least four words",
                ),
            )
        found.extend(
            Diagnostic(
                "exception-missing-symbol",
                path,
                exception.line,
                "",
                symbol,
                "the contract was renamed or deleted: remove the exception",
            )
            for symbol in exception.symbols
            if symbol not in index.symbols
        )
    return found


def registry_diagnostics(
    registry: Registry,
    index: SourceIndex,
    path: str = REGISTRY_PATH.as_posix(),
) -> list[Diagnostic]:
    """Check a parsed registry against the source.

    Parameters
    ----------
    registry: Registry
        The parsed registry.
    index: SourceIndex
        The source index.
    path: str
        The registry file for the diagnostics.

    Returns
    -------
    list[Diagnostic]
        Every finding, in registry order.

    """
    found: list[Diagnostic] = []
    for capability in registry.capabilities:
        found.extend(_capability_problems(capability, index, path))
    found.extend(_collision_problems(registry.capabilities, path))
    found.extend(_exception_problems(registry.exceptions, index, path))
    return found


def load_registry(root: Path) -> tuple[Registry, list[Diagnostic]]:
    """Read and parse the registry file of a repository.

    Parameters
    ----------
    root: Path
        The repo root.

    Returns
    -------
    tuple[Registry, list[Diagnostic]]
        The registry and the findings about its shape. A missing file is a finding too.

    """
    path = root / REGISTRY_PATH
    if not path.is_file():
        empty = Registry(capabilities=(), exceptions=())
        return empty, [_schema_problem(REGISTRY_PATH.as_posix(), 1, "the registry file is missing")]
    return parse_registry(path.read_text(encoding="utf-8"), REGISTRY_PATH.as_posix())


def check(root: Path) -> list[Diagnostic]:
    """Run every check of the registry.

    Parameters
    ----------
    root: Path
        The repo root.

    Returns
    -------
    list[Diagnostic]
        Every finding. The list is empty if the registry is right.

    """
    registry, problems = load_registry(root)
    return problems + registry_diagnostics(registry, build_index(root))


def importable_by(owner: str, layers: Sequence[str]) -> str:
    """Say which layers may import a module, from the order of the layers contract.

    Parameters
    ----------
    owner: str
        The dotted module, for example ``package.domain.summary``.
    layers: Sequence[str]
        The layer names from the highest to the lowest, as ``scripts.check_layout.layer_names`` returns them.

    Returns
    -------
    str
        A sentence about the layers that may import the module.

    """
    parts = owner.split(".")
    layer = parts[1] if len(parts) > 1 else ""
    if layer not in layers:
        return "imported by no other layer (it stands alone)"
    allowed = layers[: layers.index(layer) + 1]
    return f"importable from {', '.join(allowed)}"


def _words(text: str) -> set[str]:
    """Split a text into lower-case words, with snake_case and CamelCase names cut apart.

    Parameters
    ----------
    text: str
        Any text or name.

    Returns
    -------
    set[str]
        The lower-case words.

    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return set(re.findall(r"[a-z0-9]+", spaced.lower()))


def search(registry: Registry, index: SourceIndex, query: Sequence[str], layers: Sequence[str]) -> list[SearchHit]:
    """Find capabilities and public symbols by words.

    Parameters
    ----------
    registry: Registry
        The parsed registry.
    index: SourceIndex
        The source index.
    query: Sequence[str]
        The words to look for.
    layers: Sequence[str]
        The layer names from the highest to the lowest.

    Returns
    -------
    list[SearchHit]
        The hits with at least one matching word. Capabilities come first, then the best score, then the name.

    """
    wanted = {word for item in query for word in _words(item)}
    hits: list[SearchHit] = []
    registered = set()
    for capability in registry.capabilities:
        registered.add(capability.symbol)
        text = " ".join([capability.capability_id, capability.responsibility, capability.symbol, *capability.keywords])
        score = len(wanted & _words(text))
        symbol = index.symbols.get(capability.symbol)
        if score:
            where = (symbol.path, symbol.line) if symbol else (REGISTRY_PATH.as_posix(), capability.line)
            hits.append(
                SearchHit(
                    "capability",
                    capability.capability_id,
                    capability.owner,
                    where[0],
                    where[1],
                    score,
                    importable_by(capability.owner, layers),
                ),
            )
    for reference, symbol in index.symbols.items():
        score = len(wanted & _words(symbol.name))
        if score and reference not in registered:
            hits.append(
                SearchHit(
                    "symbol",
                    reference,
                    symbol.module,
                    symbol.path,
                    symbol.line,
                    score,
                    importable_by(symbol.module, layers),
                ),
            )
    return sorted(hits, key=lambda hit: (hit.kind != "capability", -hit.score, hit.name))


def _read_layers(root: Path) -> list[str]:
    """Read the layer names from ``pyproject.toml``.

    Parameters
    ----------
    root: Path
        The repo root.

    Returns
    -------
    list[str]
        The layers from the highest to the lowest.

    """
    return layer_names(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")))


def emit(rows: Sequence[Any], output_format: str, empty_text: str) -> None:
    """Write findings or hits to standard output.

    Parameters
    ----------
    rows: Sequence[Any]
        Attrs objects. Each has a ``render`` method.
    output_format: str
        ``text`` or ``json``.
    empty_text: str
        The line to print for no rows in the text format.

    """
    if output_format == "json":
        sys.stdout.write(orjson.dumps([attrs.asdict(row) for row in rows], option=orjson.OPT_INDENT_2).decode() + "\n")
    else:
        sys.stdout.write("\n".join(row.render() for row in rows) + "\n" if rows else f"{empty_text}\n")


def run(
    *,
    list_capabilities: bool = False,
    search_words: Sequence[str] | None = None,
    output_format: Literal["text", "json"] = "text",
    root: Path = ROOT,
) -> int:
    """Check the registry, list its capabilities or search it.

    Parameters
    ----------
    list_capabilities: bool
        Print the registered capabilities.
    search_words: Sequence[str], optional
        Find capabilities and symbols by word.
    output_format: Literal["text", "json"]
        The output format.
    root: Path
        The repo root. The default is this repository.

    Returns
    -------
    int
        The process exit code: 0 if the registry is right or the command only lists, 1 if the check found a problem.

    """
    registry, shape_problems = load_registry(root)
    index = build_index(root)
    if list_capabilities:
        listing: defaultdict[str, list[Capability]] = defaultdict(list)
        for capability in registry.capabilities:
            listing[capability.owner].append(capability)
        lines = [
            f"{owner}: {capability.capability_id} ({capability.status}) {capability.symbol} -"
            f" {capability.responsibility}"
            for owner, capabilities in sorted(listing.items())
            for capability in capabilities
        ]
        sys.stdout.write("\n".join(lines) + "\n")
        return 0
    if search_words:
        emit(
            search(registry, index, search_words, _read_layers(root)),
            output_format,
            "no match: read the owner modules before you add a shared contract",
        )
        return 0
    problems = shape_problems + registry_diagnostics(registry, index)
    emit(problems, output_format, "the registry of shared abstractions is right")
    return 1 if problems else 0


def main(argv: Sequence[str] = ()) -> int:
    """Run the command line.

    Parameters
    ----------
    argv: Sequence[str]
        The arguments. The default is none, which runs ``--check`` on this repository.

    Returns
    -------
    int
        The process exit code: 0 if the registry is right or the command only lists, 1 if the check found a problem.

    """
    parser = argparse.ArgumentParser(prog="check_abstractions", description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate the registry; this is the default mode")
    mode.add_argument("--list", action="store_true", dest="list_capabilities", help="print the registered capabilities")
    mode.add_argument("--search", nargs="+", dest="search_words", metavar="WORD", help="find capabilities by word")
    parser.add_argument("--format", choices=["text", "json"], default="text", dest="output_format")
    parser.add_argument("--root", type=Path, default=ROOT, help="the repo root")
    arguments = parser.parse_args(list(argv))
    return run(
        list_capabilities=arguments.list_capabilities,
        search_words=arguments.search_words,
        output_format=arguments.output_format,
        root=arguments.root,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
