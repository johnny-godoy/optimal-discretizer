"""Find every lint/type/coverage/test workaround in the repo together with its written reason.

A *workaround* is anything that silences a tool instead of fixing the code:

* inline comments (``noqa``, ``type: ignore``, ``pyrefly: ignore``, ``fmt: off``, ``pragma: no cover``, ...)
* ``pytest.mark.skip`` / ``skipif`` / ``xfail`` and ``pytest.skip()`` / ``xfail()``
* ignore-style settings in ``pyproject.toml`` and ``cosmic-ray.toml``

The reason lives next to the workaround, so it moves with the code and never goes stale:

* Python comments end in `` -- <reason>``: ``x = f()  # noqa: S603 -- fixed argv, never user input``
* pytest markers and calls may pass ``reason="..."`` instead
* TOML settings get a comment block directly above the key whose first line starts with ``reason:``
"""

import ast
import io
import os
import re
import tokenize
import tomllib
from pathlib import Path
from typing import Any

import attrs

ROOT = Path(__file__).resolve().parent.parent
SKIPPED_DIRS = frozenset({".git", ".venv", ".mutation", ".claude", ".agents", "__pycache__", "node_modules", "site"})
EXCLUDED_PREFIXES = (".venv/",)
MIN_REASON_WORDS = 4
MIN_REASON_CHARS = 20

COMMENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ruff",
        re.compile(r"#\s*(?:ruff:\s*(?:noqa|ignore|disable|enable|isort:\s*skip)|noqa\b|isort:\s*skip)", re.IGNORECASE),
    ),
    ("ruff", re.compile(r"#\s*fmt:\s*(?:off|on|skip)\b", re.IGNORECASE)),
    ("pyrefly", re.compile(r"#\s*(?:pyrefly:\s*ignore|type:\s*ignore)", re.IGNORECASE)),
    ("coverage", re.compile(r"#\s*pragma:\s*no\s*(?:cover|branch)", re.IGNORECASE)),
    ("cosmic-ray", re.compile(r"(?:^|\s)#\s*pragma:\s*no\s*mutate", re.IGNORECASE)),
    ("bandit", re.compile(r"#\s*nosec\b", re.IGNORECASE)),
    ("pylint", re.compile(r"#\s*pylint:\s*disable", re.IGNORECASE)),
)
REASON_SEPARATOR: re.Pattern[str] = re.compile(r"\s--\s+")
TOML_REASON: re.Pattern[str] = re.compile(r"^\s*#\s*reason:\s*(?P<text>.*)$", re.IGNORECASE)
TOML_COMMENT: re.Pattern[str] = re.compile(r"^\s*#\s?(?P<text>.*)$")
PYTEST_MARKS = frozenset({"skip", "skipif", "xfail"})
PYTEST_CALLS = frozenset({"skip", "xfail"})

# (program, file, dotted table, key, how to treat it)
# "any" = flagged whenever non-empty; "entries" = every sub-key of the setting is its own workaround.
CONFIG_TARGETS: tuple[tuple[str, str, str, str, str], ...] = (
    ("ruff", "pyproject.toml", "tool.ruff.lint", "ignore", "any"),
    ("ruff", "pyproject.toml", "tool.ruff.lint", "extend-ignore", "any"),
    ("ruff", "pyproject.toml", "tool.ruff.lint", "per-file-ignores", "entries"),
    ("ruff", "pyproject.toml", "tool.ruff.lint", "extend-per-file-ignores", "entries"),
    ("ruff", "pyproject.toml", "tool.ruff.lint", "unfixable", "any"),
    ("ruff", "pyproject.toml", "tool.ruff.format", "exclude", "any"),
    ("ruff", "pyproject.toml", "tool.ruff", "extend-exclude", "any"),
    ("ruff", "pyproject.toml", "tool.ruff", "per-file-target-version", "entries"),
    ("vulture", "pyproject.toml", "tool.vulture", "ignore_names", "any"),
    ("vulture", "pyproject.toml", "tool.vulture", "ignore_decorators", "any"),
    ("vulture", "pyproject.toml", "tool.vulture", "exclude", "any"),
    ("pyrefly", "pyproject.toml", "tool.pyrefly", "project-excludes", "any"),
    ("pyrefly", "pyproject.toml", "tool.pyrefly", "replace-imports-with-any", "any"),
    ("pyrefly", "pyproject.toml", "tool.pyrefly", "ignore-errors-in-generated-code", "any"),
    ("pyrefly", "pyproject.toml", "tool.pyrefly", "errors", "entries"),
    ("coverage", "pyproject.toml", "tool.coverage.run", "omit", "any"),
    ("coverage", "pyproject.toml", "tool.coverage.report", "omit", "any"),
    ("coverage", "pyproject.toml", "tool.coverage.report", "exclude_lines", "any"),
    ("coverage", "pyproject.toml", "tool.coverage.report", "exclude_also", "any"),
    ("pytest", "pyproject.toml", "tool.pytest.ini_options", "filterwarnings", "any"),
    ("pytest", "pyproject.toml", "tool.pytest.ini_options", "norecursedirs", "any"),
    ("cosmic-ray", "cosmic-ray.toml", "cosmic-ray", "excluded-modules", "any"),
)


@attrs.frozen
class Site:
    """One place a workaround lives, with what it silences and why."""

    program: str
    file: str
    line: int
    what: str
    reason: str

    @property
    def location(self) -> str:
        """Render the position as ``file:line``.

        Returns
        -------
        str
            The location as text.

        """
        return f"{self.file}:{self.line}"

    @property
    def reason_problem(self) -> str | None:
        """Explain why the reason is missing or too thin to be a real explanation.

        Returns
        -------
        str | None
            The problem, or None when the reason is long enough.

        """
        if not self.reason:
            return "has no reason"
        if len(self.reason) < MIN_REASON_CHARS or len(self.reason.split()) < MIN_REASON_WORDS:
            return f"reason is too thin (needs >= {MIN_REASON_WORDS} words, >= {MIN_REASON_CHARS} chars)"
        return None


def repo_files() -> list[str]:
    """List repo files as posix paths, skipping tooling directories and excluded prefixes.

    Returns
    -------
    list[str]
        Sorted repo-relative posix paths.

    """
    found: list[str] = []
    for directory, subdirs, names in os.walk(ROOT):
        subdirs[:] = [d for d in subdirs if d not in SKIPPED_DIRS]
        base = Path(directory).relative_to(ROOT)
        found += [(base / n).as_posix() for n in names]
    return sorted(n for n in found if not n.startswith(EXCLUDED_PREFIXES))


def _comments(source: str) -> dict[int, str]:
    """Map each line to its comment token, using real tokens so strings never match.

    Parameters
    ----------
    source: str
        The Python source code.

    Returns
    -------
    dict[int, str]
        Comment text by 1-based line number; empty when the source cannot be tokenized.

    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError, IndentationError, SyntaxError:
        return {}
    return {tok.start[0]: tok.string for tok in tokens if tok.type == tokenize.COMMENT}


def _split_reason(comment: str) -> tuple[str, str]:
    """Split ``# marker -- reason`` into its marker and reason.

    Parameters
    ----------
    comment: str
        The comment token.

    Returns
    -------
    tuple[str, str]
        The marker without the leading ``#``, and the reason (empty when there is none).

    """
    marker, *rest = REASON_SEPARATOR.split(comment, maxsplit=1)
    return marker.lstrip("#").strip(), rest[0].strip() if rest else ""


def comment_sites(name: str, comments: dict[int, str]) -> list[Site]:
    """Find suppression comments in a file's comments.

    Parameters
    ----------
    name: str
        The repo-relative path of the file.
    comments: dict[int, str]
        The comment token of each line.

    Returns
    -------
    list[Site]
        Sites of suppression comments.

    """
    sites: list[Site] = []
    for line, comment in comments.items():
        marker, reason = _split_reason(comment)
        sites += [
            Site(program, name, line, marker, reason)
            for program, pattern in COMMENT_PATTERNS
            if pattern.search(comment)
        ]
    return sites


def _dotted(node: ast.expr) -> str:
    """Return ``a.b.c`` for an attribute chain, else an empty string.

    Parameters
    ----------
    node: ast.expr
        The expression to render.

    Returns
    -------
    str
        The dotted name.

    """
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _keyword_reason(node: ast.AST) -> str:
    """Read a literal ``reason="..."`` argument from a call.

    Parameters
    ----------
    node: ast.AST
        The node to inspect.

    Returns
    -------
    str
        The reason, or an empty string when the node is not a call with a literal string ``reason``.

    """
    if not isinstance(node, ast.Call):
        return ""
    for keyword in node.keywords:
        if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value.strip()
    return ""


def pytest_sites(name: str, source: str, comments: dict[int, str]) -> list[Site]:
    """Find ``pytest.mark.skip*``/``xfail`` markers and ``pytest.skip()``/``xfail()`` calls.

    The reason is the literal ``reason=`` argument, else the `` -- <reason>`` of a comment on the same line.

    Parameters
    ----------
    name: str
        The repo-relative path of the file.
    source: str
        The source code of the file.
    comments: dict[int, str]
        The comment token of each line.

    Returns
    -------
    list[Site]
        Sites of pytest skip/xfail usage.

    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: dict[tuple[int, str], Site] = {}
    for node in ast.walk(tree):
        target = node.func if isinstance(node, ast.Call) else node if isinstance(node, ast.Attribute) else None
        if target is None:
            continue
        dotted = _dotted(target)
        parts = dotted.split(".")
        is_mark = parts[:2] == ["pytest", "mark"] and parts[2:] != [] and parts[2] in PYTEST_MARKS
        is_call = isinstance(node, ast.Call) and parts[0] == "pytest" and parts[1:2] != [] and parts[1] in PYTEST_CALLS
        if is_mark or is_call:
            line = node.lineno
            reason = _keyword_reason(node) or _split_reason(comments.get(line, ""))[1]
            # a call and its own func attribute are both visited, so keep the one that read the reason
            if (line, dotted) not in found or reason:
                found[line, dotted] = Site("pytest", name, line, dotted, reason)
    return list(found.values())


def _toml_reason(lines: list[str], key_line: int) -> str:
    """Read the ``# reason: ...`` comment block that sits directly above a key.

    Parameters
    ----------
    lines: list[str]
        The lines of the TOML file.
    key_line: int
        The 1-based line of the key.

    Returns
    -------
    str
        The reason (continuation comment lines joined by spaces), or an empty string when there is none.

    """
    block: list[str] = []
    index = key_line - 2
    while index >= 0 and (match := TOML_COMMENT.match(lines[index])):
        block.append(match["text"].strip())
        index -= 1
    block.reverse()
    first = TOML_REASON.match(f"# {block[0]}") if block else None
    if first is None:
        return ""
    return " ".join([first["text"].strip(), *block[1:]]).strip()


def config_sites(name: str, source: str) -> list[Site]:
    """Find ignore-style settings in a TOML config; the line is the key's own line.

    Parameters
    ----------
    name: str
        The repo-relative path of the file.
    source: str
        The contents of the file.

    Returns
    -------
    list[Site]
        Sites of ignore-style settings.

    """
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return []
    lines = source.splitlines()
    sites: list[Site] = []
    for program, file, table, key, mode in CONFIG_TARGETS:
        if file != name:
            continue
        section: Any = data
        for part in table.split("."):
            section = section.get(part, {}) if isinstance(section, dict) else {}
        value = section.get(key) if isinstance(section, dict) else None
        if not value:
            continue
        own_table = f"{table}.{key}"
        if mode == "entries" and isinstance(value, dict) and _key_line(lines, own_table, ""):
            found = [(f"{own_table}.{sub}", _key_line(lines, own_table, str(sub))) for sub in value]
        else:
            found = [(own_table, _key_line(lines, table, key))]
        sites += [Site(program, name, line, what, _toml_reason(lines, line)) for what, line in found if line]
    return sites


def _key_line(lines: list[str], table: str, key: str) -> int:
    """Find the 1-based line of ``key =`` inside ``[table]``, or of the header itself when key is empty.

    Parameters
    ----------
    lines: list[str]
        The lines of the TOML file.
    table: str
        The dotted name of the table.
    key: str
        The key to look for. If empty, the line of the table header is returned.

    Returns
    -------
    int
        The line number, or 0 when not found.

    """
    header = re.compile(rf"^\s*\[\s*{re.escape(table)}\s*]\s*(?:#.*)?$")
    any_header = re.compile(r"^\s*\[")
    assignment = re.compile(rf"""^\s*["']?{re.escape(key)}["']?\s*=""")
    in_table = False
    for number, text in enumerate(lines, start=1):
        if header.match(text):
            if not key:
                return number
            in_table = True
        elif any_header.match(text):
            in_table = False
        elif in_table and assignment.match(text):
            return number
    return 0


def find_sites(files: list[str] | None = None) -> list[Site]:
    """Collect every workaround site in the repo.

    Parameters
    ----------
    files: list[str] | None
        The repo-relative paths of the files to scan; every repo file when omitted.

    Returns
    -------
    list[Site]
        All workaround sites, ordered by file and line.

    """
    sites: list[Site] = []
    for name in repo_files() if files is None else files:
        path = ROOT / name
        if path.suffix == ".py":
            source = path.read_text(encoding="utf-8")
            comments = _comments(source)
            sites += comment_sites(name, comments)
            sites += pytest_sites(name, source, comments)
        elif path.suffix == ".toml":
            sites += config_sites(name, path.read_text(encoding="utf-8"))
    return sorted(sites, key=lambda site: (site.file, site.line, site.program))
