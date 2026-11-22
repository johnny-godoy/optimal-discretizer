"""Run cosmic-ray mutation testing in parallel and report the mutation score.

cosmic-ray mutates the source tree in place, so every shard works on its own copy of the project. The work items of
each module in the main session are split over the shards, executed concurrently, and the results are merged back into
the main session for reporting. A shard runs the tests of its own module first, because they kill most mutants of that
module. A progress line appears every minute.

Usage: ``uv run python scripts/mutation.py [shards] [--base REF | --module PATH ...]``. With ``--base``, only the
mutants on the lines that changed since ``REF`` run. With ``--module``, all mutants of the given modules run. Exits
non-zero if any mutant survives.
"""

import argparse  # ruff: ignore[banned-api] -- the scripts run with the dev group only, which has no command-line library
import itertools
import os
import re
import shlex
import shutil
import sqlite3
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- must launch cosmic-ray and the interpreter as subprocesses
import sys
import tempfile
import threading
import time
import tomllib
from collections.abc import Collection, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import attrs
import orjson
import structlog
from coverage import CoverageData

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)
ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "cosmic-ray.toml"
SESSION = ROOT / ".mutation" / "session.sqlite"
COPIED = ("src", "tests", "scripts", "pyproject.toml", "cosmic-ray.toml")
# the package under mutation, for example ``src/package``
MODULE_PATH = tomllib.loads(CONFIG.read_text())["cosmic-ray"]["module-path"]
POLL_SECONDS = 60
# the new side of a hunk header of ``git diff -U0``: ``+start`` or ``+start,count``
HUNK: re.Pattern[str] = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")


@attrs.frozen
class Shard:
    """A copy of the project that runs a share of the work items of one module.

    Attributes
    ----------
    path: Path
        The directory of the shard.
    module: str
        The path of the module, relative to the project root.

    """

    path: Path
    module: str


def run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    """Run a command and collect its output, whatever its exit code.

    Parameters
    ----------
    *args: str
        The command and its arguments.
    cwd: Path
        The working directory.
    env: dict[str, str], optional
        The environment of the command. Defaults to the current environment.

    Returns
    -------
    str
        The standard output followed by the standard error.

    """
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed argv from sys.executable, never untrusted input
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout + result.stderr


def parse_changed_lines(diff: str) -> dict[str, set[int]]:
    """Read the changed lines of each file from the output of ``git diff -U0``.

    Parameters
    ----------
    diff: str
        The output of ``git diff -U0``.

    Returns
    -------
    dict[str, set[int]]
        The line numbers on the new side, by the path of the file. A file with deletions only has an empty set.

    """
    lines: dict[str, set[int]] = {}
    current: set[int] = set()
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = lines.setdefault(line.removeprefix("+++ ").removeprefix("b/"), set())
        elif match := HUNK.match(line):
            start, count = int(match[1]), int(match[2] or "1")
            current.update(range(start, start + count))
    return lines


def changed_lines(base: str) -> dict[str, set[int]]:
    """List the changed lines of each source module between a base revision and HEAD.

    Parameters
    ----------
    base: str
        The base revision, for example ``origin/main``. The comparison starts at the merge base.

    Returns
    -------
    dict[str, set[int]]
        The changed line numbers, by the path of the module relative to the project root.

    """
    diff = run("git", "diff", "-U0", "--no-color", "--no-ext-diff", f"{base}...HEAD", "--", MODULE_PATH)
    return {
        path: lines
        for path, lines in parse_changed_lines(diff).items()
        if path.endswith(".py") and (ROOT / path).exists()
    }


def session_modules(session: Path) -> set[str]:
    """List the modules that have work items in a session.

    Parameters
    ----------
    session: Path
        The cosmic-ray session.

    Returns
    -------
    set[str]
        The paths of the modules, relative to the project root.

    """
    with closing(sqlite3.connect(session)) as db, db:  # closing releases the file, db commits
        return {row[0] for row in db.execute("SELECT DISTINCT module_path FROM mutation_specs")}


def keep_lines(session: Path, lines: Mapping[str, Collection[int]]) -> None:
    """Drop the work items of all mutants that touch none of the given lines.

    Parameters
    ----------
    session: Path
        The cosmic-ray session.
    lines: Mapping[str, Collection[int]]
        The line numbers to keep, by the path of the module. A module that is not a key loses all its mutants.

    """
    with closing(sqlite3.connect(session)) as db, db:  # closing releases the file, db commits
        specs = db.execute("SELECT job_id, module_path, start_pos_row, end_pos_row FROM mutation_specs").fetchall()
        dropped = [
            (job,)
            for job, module, start, end in specs
            if not any(row in lines.get(module, ()) for row in range(start, end + 1))
        ]
        db.executemany("DELETE FROM work_items WHERE job_id = ?", dropped)
        db.executemany("DELETE FROM mutation_specs WHERE job_id = ?", dropped)
        db.commit()


def keep_modules(session: Path, modules: Collection[str]) -> None:
    """Drop the work items of all modules except the given ones.

    Parameters
    ----------
    session: Path
        The cosmic-ray session.
    modules: Collection[str]
        The paths of the modules to keep.

    """
    keep_lines(session, {module: range(1, sys.maxsize) for module in modules})


def make_shard(workdir: Path, module: str, index: int, shards: int) -> Shard:
    """Copy the project into its own directory, together with the share of the work items of the shard.

    Parameters
    ----------
    workdir: Path
        The directory that holds the shards.
    module: str
        The path of the module whose work items the shard runs.
    index: int
        The index of the shard among the shards of the module.
    shards: int
        The number of shards of the module.

    Returns
    -------
    Shard
        The shard.

    """
    path = workdir / f"{Path(module).stem}-{index}"
    path.mkdir()
    for name in COPIED:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, path / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(source, path / name)
    session = path / "session.sqlite"
    shutil.copy(SESSION, session)
    with closing(sqlite3.connect(session)) as db, db:  # closing releases the file, db commits
        # keep every ``shards``-th job of the module; results of earlier runs are dropped so they are recomputed
        # jobs the pragma filter skipped keep their result in the main session and are not executed again
        skipped = {row[0] for row in db.execute("SELECT job_id FROM work_results WHERE worker_outcome = 'SKIPPED'")}
        db.execute("DELETE FROM work_results")
        job_ids = [row[0] for row in db.execute("SELECT job_id FROM work_items ORDER BY job_id")]
        of_module = {row[0] for row in db.execute("SELECT job_id FROM mutation_specs WHERE module_path = ?", (module,))}
        candidates = [job for job in job_ids if job in of_module and job not in skipped]
        mine = set(candidates[index::shards])
        dropped = [(job,) for job in job_ids if job not in mine]
        db.executemany("DELETE FROM mutation_specs WHERE job_id = ?", dropped)
        db.executemany("DELETE FROM work_items WHERE job_id = ?", dropped)
    return Shard(path, module)


def build_coverage_map(
    coverage_file: str | Path,
    root: Path,
    modules: Collection[str],
) -> dict[str, dict[str, list[str]]]:
    """Read the tests that execute each line of the given modules from a coverage file with test contexts.

    Parameters
    ----------
    coverage_file: str | Path
        The data file of a pytest run with ``--cov-context=test``.
    root: Path
        The project root. The keys of the map are module paths relative to it.
    modules: Collection[str]
        The paths of the modules to read, relative to the project root.

    Returns
    -------
    dict[str, dict[str, list[str]]]
        For each module, the sorted node ids of the tests that execute each line. The line numbers are strings,
        because the map is written as JSON.

    """
    data = CoverageData(str(coverage_file))
    data.read()
    result: dict[str, dict[str, list[str]]] = {}
    for measured in data.measured_files():
        if not Path(measured).is_relative_to(root):
            continue
        module = Path(measured).relative_to(root).as_posix()
        if module not in modules:
            continue
        result[module] = {
            str(line): sorted({context.split("|")[0] for context in contexts if context})
            for line, contexts in data.contexts_by_lineno(measured).items()
        }
    return result


def run_baseline(workdir: Path, modules: Collection[str]) -> int:
    """Run the tests on the unmutated code, and write the coverage map for the shards.

    Parameters
    ----------
    workdir: Path
        The directory that holds the shards. The map goes to ``coverage.json`` in it.
    modules: Collection[str]
        The paths of the modules under mutation. The map holds only these.

    Returns
    -------
    int
        The exit code of the tests: non-zero if a test fails on the unmutated code.

    """
    command = shlex.split(tomllib.loads(CONFIG.read_text())["cosmic-ray"]["test-command"])
    if command[0] == "python":
        command[0] = sys.executable
    data = workdir / ".coverage"
    baseline = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- the test command of cosmic-ray.toml, never untrusted input
        [*command, f"--cov={Path(MODULE_PATH).name}", "--cov-context=test", "--cov-report="],
        cwd=ROOT,
        env={**os.environ, "COVERAGE_FILE": str(data)},
        capture_output=True,
        text=True,
        check=False,
    )
    if baseline.returncode:
        logger.error("Baseline failed", output=baseline.stdout[-5000:] + baseline.stderr[-5000:])
        return baseline.returncode
    coverage = build_coverage_map(data, ROOT, modules)
    (workdir / "coverage.json").write_bytes(orjson.dumps(coverage))
    return 0


def exec_shard(shard: Shard, workdir: Path) -> None:
    """Execute the work items of a shard against the copy of the project of that shard.

    Parameters
    ----------
    shard: Shard
        The shard.
    workdir: Path
        The directory that holds the shards and the coverage map of the baseline.

    """
    env = {
        **os.environ,
        "PYTHONPATH": str(shard.path / "src"),
        # tests/unit/conftest.py runs the tests that execute the mutated statements first, then the tests of this
        # module, so a killed mutant stops the run early
        "MUTATION_FIRST": Path(shard.module).stem,
        "MUTATION_MODULE": shard.module,
        "MUTATION_ORIGINAL": str(ROOT),
        "MUTATION_COVERAGE": str(workdir / "coverage.json"),
    }
    started = time.monotonic()
    run(sys.executable, "-m", "cosmic_ray.cli", "exec", "cosmic-ray.toml", "session.sqlite", cwd=shard.path, env=env)
    logger.info("shard done", module=shard.module, shard=shard.path.name, seconds=round(time.monotonic() - started))


def count_results(sessions: Sequence[Path], seen: dict[Path, tuple[int, int]]) -> tuple[int, int]:
    """Count the finished and the surviving mutants of the sessions of the shards.

    Parameters
    ----------
    sessions: Sequence[Path]
        The sessions of the shards.
    seen: dict[Path, tuple[int, int]]
        The last count of each session. A session that is locked for writing keeps its last count.

    Returns
    -------
    tuple[int, int]
        The number of finished mutants and the number of surviving mutants.

    """
    for session in sessions:
        try:
            with closing(sqlite3.connect(session, timeout=5)) as db, db:  # closing releases the file, db commits
                query = "SELECT COUNT(*), COALESCE(SUM(test_outcome = 'SURVIVED'), 0) FROM work_results"
                seen[session] = db.execute(query).fetchone()
        except sqlite3.OperationalError:
            logger.warning("session locked", session=str(session))
    return sum(done for done, _ in seen.values()), sum(survived for _, survived in seen.values())


def report_progress(sessions: Sequence[Path], total: int, stop: threading.Event) -> None:
    """Log the progress of the shards every ``POLL_SECONDS`` seconds, until the event is set.

    Parameters
    ----------
    sessions: Sequence[Path]
        The sessions of the shards.
    total: int
        The number of mutants that the shards run.
    stop: threading.Event
        The event that ends the loop.

    """
    started = time.monotonic()
    seen: dict[Path, tuple[int, int]] = {}  # a dict, because count_results writes to it
    while not stop.wait(POLL_SECONDS):
        done, survived = count_results(sessions, seen)
        elapsed = time.monotonic() - started
        eta = round(elapsed / done * (total - done)) if done else None
        logger.info("progress", done=done, total=total, survived=survived, elapsed_s=round(elapsed), eta_s=eta)


def merge_results(sessions: Sequence[Path]) -> None:
    """Copy the results of the shards into the main session.

    Parameters
    ----------
    sessions: Sequence[Path]
        The sessions of the shards.

    """
    with closing(sqlite3.connect(SESSION)) as db, db:  # closing releases the file, db commits
        for session in sessions:
            db.execute("ATTACH DATABASE ? AS shard", (str(session),))
            db.execute("INSERT OR REPLACE INTO work_results SELECT * FROM shard.work_results")
            db.commit()
            db.execute("DETACH DATABASE shard")


def count_mutants() -> int:
    """Count the mutants that the main session still has to run.

    Returns
    -------
    int
        The number of work items, without the items that the pragma filter skipped.

    """
    with closing(sqlite3.connect(SESSION)) as db, db:  # closing releases the file, db commits
        return int(
            db.execute(
                "SELECT COUNT(*) FROM work_items WHERE job_id NOT IN "
                "(SELECT job_id FROM work_results WHERE worker_outcome = 'SKIPPED')",
            ).fetchone()[0],
        )


def select_mutants(base: str | None, modules: Sequence[str] | None) -> None:
    """Drop the work items of the main session that the run does not need.

    Parameters
    ----------
    base: str, optional
        Keep only the mutants on the lines that changed since this revision.
    modules: Sequence[str], optional
        Keep only the mutants of these modules. Without ``base`` and ``modules``, all mutants stay.

    """
    if base:
        lines = changed_lines(base)
        keep_lines(SESSION, lines)
        logger.info("changed lines", modules=sorted(lines), base=base)
    elif modules:
        keep_modules(SESSION, modules)
        logger.info("partial run", modules=sorted(modules))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the mutation testing in shards.

    Parameters
    ----------
    argv: Sequence[str], optional
        The arguments. The default is the arguments of the process.

    Returns
    -------
    int
        The exit code: non-zero if the baseline fails or any mutant survives.

    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shards", nargs="?", type=int, default=os.cpu_count() or 1)
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--base", help="mutate only the lines that changed since this revision")
    which.add_argument("--module", action="append", help="mutate only this module; repeat for more modules")
    args = parser.parse_args(argv)
    shards: int = args.shards
    module: list[str] | None = args.module
    SESSION.parent.mkdir(exist_ok=True)
    SESSION.unlink(missing_ok=True)
    run(sys.executable, "-m", "cosmic_ray.cli", "init", str(CONFIG), str(SESSION))
    # lines marked ``# pragma: no mutate`` hold mutants that are equivalent to the original code
    run(sys.executable, "-m", "cosmic_ray.tools.filters.pragma_no_mutate", str(SESSION))
    missing = sorted(path for path in module or () if not (ROOT / path).is_file())
    if missing:
        sys.stderr.write(f"no such module: {', '.join(missing)}\n")
        return 2
    select_mutants(args.base, module)
    modules = sorted(session_modules(SESSION))
    if not modules:
        logger.info("no mutants to run")
        return 0
    total = count_mutants()
    logger.info("mutants", total=total, modules=modules, shards=shards)

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        failed = run_baseline(workdir, modules)
        if failed:
            return failed

        prepared = [make_shard(workdir, module, i, shards) for module in modules for i in range(shards)]
        sessions = [shard.path / "session.sqlite" for shard in prepared]
        stop = threading.Event()
        monitor = threading.Thread(target=report_progress, args=(sessions, total, stop))
        monitor.start()
        try:
            with ThreadPoolExecutor(max_workers=shards) as pool:
                list(pool.map(exec_shard, prepared, itertools.repeat(workdir)))
        finally:
            stop.set()
            monitor.join()
        merge_results(sessions)

    rate = float(run(sys.executable, "-m", "cosmic_ray.tools.survival_rate", str(SESSION)).strip())
    logger.info("mutation score", survival_rate=rate)
    return int(rate > 0)


if __name__ == "__main__":
    sys.exit(main())
