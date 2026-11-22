"""Tests for the choice of the mutants that the mutation run executes."""

import sqlite3
from contextlib import closing
from pathlib import Path

from coverage import CoverageData
from scripts import mutation

DIFF = """\
diff --git a/src/pkg/a.py b/src/pkg/a.py
index 1111111..2222222 100644
--- a/src/pkg/a.py
+++ b/src/pkg/a.py
@@ -3 +3 @@ def f():
-    return 1
+    return 2
@@ -10,0 +11,3 @@ def g():
+    x = 1
+    y = 2
+    return x + y
diff --git a/src/pkg/b.py b/src/pkg/b.py
--- a/src/pkg/b.py
+++ b/src/pkg/b.py
@@ -5,2 +4,0 @@ def h():
-    a = 1
-    b = 2
"""


def make_session(path: Path, specs: list[tuple[str, str, int, int]]) -> Path:
    """Write a session with the tables of cosmic-ray that the mutation run reads.

    Parameters
    ----------
    path: Path
        The directory of the session.
    specs: list[tuple[str, str, int, int]]
        The job id, the module, the first row and the last row of each mutant.

    Returns
    -------
    Path
        The session.

    """
    session = path / "session.sqlite"
    with closing(sqlite3.connect(session)) as db, db:  # closing releases the file, db commits
        db.execute("CREATE TABLE work_items (job_id VARCHAR PRIMARY KEY)")
        db.execute(
            "CREATE TABLE mutation_specs (module_path VARCHAR, start_pos_row INTEGER, end_pos_row INTEGER, "
            "job_id VARCHAR PRIMARY KEY)",
        )
        db.executemany("INSERT INTO work_items VALUES (?)", [(job,) for job, *_ in specs])
        db.executemany(
            "INSERT INTO mutation_specs VALUES (?, ?, ?, ?)",
            [(module, start, end, job) for job, module, start, end in specs],
        )
    return session


def jobs(session: Path) -> set[str]:
    with closing(sqlite3.connect(session)) as db, db:  # closing releases the file, db commits
        items = {row[0] for row in db.execute("SELECT job_id FROM work_items")}
        assert items == {row[0] for row in db.execute("SELECT job_id FROM mutation_specs")}
        return items


def test_parse_changed_lines_reads_the_new_side_of_each_hunk() -> None:
    assert mutation.parse_changed_lines(DIFF) == {"src/pkg/a.py": {3, 11, 12, 13}, "src/pkg/b.py": set()}


def test_parse_changed_lines_of_an_empty_diff_is_empty() -> None:
    assert mutation.parse_changed_lines("") == {}


def test_keep_lines_keeps_only_the_mutants_that_touch_a_changed_line(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        [
            ("on", "src/pkg/a.py", 3, 3),
            ("spans", "src/pkg/a.py", 9, 11),
            ("before", "src/pkg/a.py", 2, 2),
            ("after", "src/pkg/a.py", 14, 14),
            ("other", "src/pkg/b.py", 3, 3),
        ],
    )
    mutation.keep_lines(session, {"src/pkg/a.py": {3, 11, 12, 13}})
    assert jobs(session) == {"on", "spans"}


def test_keep_modules_keeps_every_mutant_of_the_given_modules(tmp_path: Path) -> None:
    session = make_session(tmp_path, [("a", "src/pkg/a.py", 1, 1), ("b", "src/pkg/b.py", 900, 901)])
    mutation.keep_modules(session, ["src/pkg/b.py"])
    assert jobs(session) == {"b"}


def test_build_coverage_map_lists_the_tests_of_each_line_of_the_given_modules(tmp_path: Path) -> None:
    module = tmp_path / "src" / "pkg" / "m.py"
    other = tmp_path / "src" / "pkg" / "other.py"
    data = CoverageData(str(tmp_path / ".coverage"))
    data.set_context("")
    data.add_lines({str(module): [1]})
    for context, lines in (("t.py::a|setup", [2]), ("t.py::a|run", [2, 3]), ("t.py::b|run", [3])):
        data.set_context(context)
        data.add_lines({str(module): lines, str(other): lines})
    data.write()
    coverage = mutation.build_coverage_map(tmp_path / ".coverage", tmp_path, {"src/pkg/m.py"})
    assert coverage == {"src/pkg/m.py": {"1": [], "2": ["t.py::a"], "3": ["t.py::a", "t.py::b"]}}
