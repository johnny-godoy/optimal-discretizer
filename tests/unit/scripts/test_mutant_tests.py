"""Tests for the choice of the tests that run first under a mutant."""

from scripts import mutant_tests

SOURCE = """\
def f(x):
    if x > 0:
        return 1
    total = (
        x
        + 2
    )
    return total


LIMIT = 3
"""


def test_mutated_lines_names_the_changed_lines_of_the_original() -> None:
    mutated = SOURCE.replace("x > 0", "x >= 0").replace("+ 2", "- 2")
    assert mutant_tests.mutated_lines(SOURCE, mutated) == {2, 6}


def test_mutated_lines_of_an_insertion_is_the_line_after_it() -> None:
    lines = SOURCE.splitlines(keepends=True)
    mutated = "".join([*lines[:2], "    pass\n", *lines[2:]])
    assert mutant_tests.mutated_lines(SOURCE, mutated) == {3}


def test_mutated_lines_of_equal_sources_is_empty() -> None:
    assert mutant_tests.mutated_lines(SOURCE, SOURCE) == set()


def test_statement_lines_widens_a_line_to_its_innermost_statement() -> None:
    assert mutant_tests.statement_lines(SOURCE, {6}) == {4, 5, 6, 7}
    assert mutant_tests.statement_lines(SOURCE, {3}) == {3}
    assert mutant_tests.statement_lines(SOURCE, {2}) == {2, 3}


def test_statement_lines_keeps_a_line_outside_all_statements() -> None:
    assert mutant_tests.statement_lines(SOURCE, {9}) == {9}


def test_covering_tests_finds_the_tests_of_every_line_of_the_mutated_statement() -> None:
    coverage = {"2": ["t::a"], "3": ["t::b"], "4": ["t::c"], "11": ["t::d"]}
    assert mutant_tests.covering_tests(coverage, SOURCE, SOURCE.replace("x > 0", "x < 0")) == {"t::a", "t::b"}
    assert mutant_tests.covering_tests(coverage, SOURCE, SOURCE.replace("+ 2", "+ 3")) == {"t::c"}
    assert mutant_tests.covering_tests(coverage, SOURCE, SOURCE) == set()
