"""Find the tests that execute the lines of a mutant, so that the mutation run can run them first.

``scripts/mutation.py`` runs the test baseline with one coverage context for each test. It writes a coverage map with
the tests that execute each line of each module (``build_coverage_map``). Under a mutant, ``tests/unit/conftest.py``
compares the mutated module with the original, finds the tests that execute the changed statements, and runs them
first. The run stops at the first failure, so a killed mutant runs only a few tests. A surviving mutant still runs
every test, so the order changes the time of the run but not its result.
"""

import ast
import difflib
from collections.abc import Collection, Mapping, Sequence


def mutated_lines(original: str, mutated: str) -> set[int]:
    """List the lines of the original source that a mutation changes.

    Parameters
    ----------
    original: str
        The source of the module.
    mutated: str
        The source of the module with the mutation applied.

    Returns
    -------
    set[int]
        The numbers of the changed lines of the original source. An insertion counts as a change of the line after it.

    """
    matcher = difflib.SequenceMatcher(None, original.splitlines(), mutated.splitlines(), autojunk=False)
    lines: set[int] = set()
    for tag, start, end, _, _ in matcher.get_opcodes():
        if tag != "equal":
            lines.update(range(start + 1, max(end, start + 1) + 1))
    return lines


def statement_lines(source: str, lines: Collection[int]) -> set[int]:
    """Widen each line to all lines of the innermost statement that contains it.

    Coverage records a statement on one of its lines, and a mutation can change another line of the same statement.
    All lines of the statement then give every test that can reach the mutation.

    Parameters
    ----------
    source: str
        The source of the module.
    lines: Collection[int]
        The line numbers to widen.

    Returns
    -------
    set[int]
        The line numbers of the statements. A line outside all statements stays as it is.

    """
    spans = [
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.stmt)
    ]
    result: set[int] = set()
    for line in lines:
        containing = [(start, end) for start, end in spans if start <= line <= end]
        if not containing:
            result.add(line)
            continue
        start, end = min(containing, key=lambda span: span[1] - span[0])
        result.update(range(start, end + 1))
    return result


def covering_tests(coverage: Mapping[str, Sequence[str]], original: str, mutated: str) -> set[str]:
    """Find the tests that execute a statement that a mutation changes.

    Parameters
    ----------
    coverage: Mapping[str, Sequence[str]]
        The node ids of the tests that execute each line of the module, keyed by the line number as a string.
    original: str
        The source of the module.
    mutated: str
        The source of the module with the mutation applied.

    Returns
    -------
    set[str]
        The node ids of the tests. The set is empty if the sources are equal or no test executes the statements.

    """
    lines = statement_lines(original, mutated_lines(original, mutated))
    return {test for line in lines for test in coverage.get(str(line), ())}
