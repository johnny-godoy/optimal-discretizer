# Preferred libraries

The project uses one library for each need, chosen for this stack, not for its popularity. Do not add a replaced
library back. The single source of the banned imports is `[tool.ruff.lint.flake8-tidy-imports.banned-api]` in
`pyproject.toml`: each entry names the module and its replacement. Read that table when you need the list, and do not
copy it here, because a copy goes stale. Ruff fails on a banned import. An exception is an inline
`# ruff: ignore[banned-api] -- <reason>`.

`scripts/check_layout.py` fails on the files of a replaced tool (`BANNED_FILES`: a `Makefile`, a `requirements.txt`,
a pickled model, a Jupyter notebook). The choices below have no import to ban, so only this rule enforces them:

| Need | Use | Not |
| --- | --- | --- |
| Packaging, environments | uv | pip, poetry, pipenv |
| Git hooks | prek | pre-commit |
| Lint, format and static types | ruff (select ALL), pyrefly (strict) | black, isort, flake8, pylint, mypy, pyright |
| Tests of the code in the docs | sybil | pytest's `--doctest-modules` and `--doctest-glob` |
| Docs, changelog, mutation testing | Zensical, scriv fragments, cosmic-ray | Sphinx, MkDocs, towncrier, mutmut |

## Logging (`structlog`)

- Module-level logger: `logger = structlog.get_logger(__name__)`.
- Log an event name plus key-value pairs (`logger.info("usage", what=what, count=n)`). Never %-format or f-string the
  message, because the event name is what a log query matches.
- Tests capture logs with `structlog.testing.capture_logs()` and assert on the event dicts, not on `caplog`.

## JSON (`orjson`)

- `orjson.loads` accepts `bytes` or `str`. Prefer `path.read_bytes()` over `read_text()`.
- `orjson.dumps` returns `bytes`: write with `write_bytes`, and use `option=orjson.OPT_INDENT_2` instead of `indent=2`.
- Catch `orjson.JSONDecodeError`.

## Data classes (`attrs`) and wire schemas (`msgspec`)

- Use `@attrs.frozen` (or `@attrs.define`) for the types of the domain, with `attrs.field` and `attrs.asdict`.
- Use a `msgspec.Struct` only at the edge, for a body, a message or a config file that crosses a process boundary.
  Convert it to the attrs type in the adapter or the controller, so the domain does not depend on the wire format.

## Run-time types (`beartype`)

- `src/optimal_discretizer/__init__.py` calls `beartype_this_package()` before it imports any submodule, so every
  function in `optimal_discretizer` checks its hints. Keep that call first. A module imported earlier stays unchecked.
- Do not add `@beartype` to a function in `optimal_discretizer`. The hook already covers it.
- A hint that is wrong fails at run time. Fix the hint (see `types.md`), and do not remove the check.
- Pytest turns `BeartypeClawDecorWarning` into an error, because beartype skips a function that it cannot decorate.
- Checks of annotated variables are off (`claw_is_pep526=False`): structlog's lazy logger proxy fails its own hint.
- An import that only a hint uses is a run-time import, because beartype reads the hint. So ruff's rules that move
  such imports into a `TYPE_CHECKING` block are off.

## Async code (`anyio`, `stamina`)

- Start concurrent work in an `anyio.create_task_group()`, so that an error cancels the sibling tasks and nothing
  outlives its scope.
- Retry a call that can fail for a moment with `@stamina.retry(on=..., attempts=...)`. Tests call
  `stamina.set_testing(True)`, so a retry does not wait.
- Write async tests with `@pytest.mark.anyio`.

## Exceptions

- `.github/scripts/ci_report.py` runs under the runner's bare `python3` with no project environment, so it stays
  standard-library only (`json`), with an inline `# ruff: ignore[banned-api]` and its reason.
- The maintenance scripts in `scripts/` run with the standard library and the dev group, which has no command-line
  library, so they use `argparse` with an inline `# ruff: ignore[banned-api]` and its reason.
