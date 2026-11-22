# prek and ignores

## Run prek before finishing

- After changing any file, run `prek run --all-files` and fix every failure before reporting the task done or committing.
- Files not yet tracked by git are skipped by `--all-files`; run `prek run --files <paths>` for those.
- Hooks may rewrite files (ruff fixes, formatters). Re-run until it passes cleanly, and re-read files you plan to edit again.
- `.claude/settings.json` runs `prek run --files <file>` after each `Edit`, `Write` or `NotebookEdit`. If it reports a failure, fix it before the next edit. It checks one file, so the full `prek run --all-files` is still needed before you finish.
- Never bypass hooks (`--no-verify`, `SKIP=...`, or removing/editing a hook to make it pass) unless the user explicitly asks.
- Do not report "done" with prek failing. If a failure is unrelated or cannot be fixed, say so with the output.

## Cooldown exemptions expire

`exclude-newer-package` in `pyproject.toml` skips the 7-day uv cutoff for one package, for example to take a security
fix. Use it only for a security fix, and write the `reason:` block above it. The `check-exclusions` hook fails when the
locked version is older than the cutoff. Then delete the entry and run `uv lock`. Do not edit the hook to keep an entry.

## Workarounds need a written reason next to them

A workaround silences a tool instead of fixing the code: `# noqa`, `# type: ignore`, `# pyrefly: ignore`, `# fmt: off`,
`# pragma: no cover`, `# pragma: no mutate`, `pytest.mark.skip/skipif/xfail`, `pytest.skip()`, and ignore/exclude/omit
settings in `pyproject.toml` or `cosmic-ray.toml`. Fix the root cause first; a workaround is a last resort.

### Scope: inline first, config only for recurring patterns

- A one-off or a handful of occurrences gets an **inline** ignore (`# noqa: RULE`, `# pyrefly: ignore[...]`, ...) on the
  exact line, so each one is vetted at the place it applies and carries its own reason.
- Config-level ignores (`per-file-ignores`, `ignore`, `exclude`, `omit`, `ignore_names`, ... in `pyproject.toml` or
  `cosmic-ray.toml`) are only for a **recurring pattern** that would otherwise need the same inline ignore over and over
  (e.g. `assert` in `tests/**`). Never use them to silence a rule for one function or a few lines in a source file.
- Before adding a config-level ignore, check how many places it would cover; if it is only a few, go inline. If an
  existing config-level ignore covers only a few places, convert it to inline ignores and remove the config entry.
- The reason of a config-level ignore must name the recurring pattern it covers.

### Where the reason goes

The reason lives with the workaround, so it moves with the code and cannot go stale. There is no separate registry.

- **Python comments** end in ` -- <reason>`: `run(argv)  # noqa: S603 -- fixed argv, never untrusted input`.
- **pytest markers and calls** take `reason="..."`, or the same ` -- <reason>` comment on the line.
- **TOML settings** get a comment block directly above the key; its first line starts with `reason:`:

  ```toml
  # reason: recurring pattern in tests/: bare assert and literal expected values are how pytest tests are written.
  "tests/**/*.py" = ["assert", "magic-value-comparison"]
  ```

The reason must say why it cannot be fixed, not restate what the ignore does (at least 4 words and 20 characters). Never
invent a reason; ask the user if unsure. Remove a workaround whenever the tool passes without it.

Verify with `uv run python -m scripts.check_ignores` (also runs as the `check-ignores` hook). To audit all of them in one
place, run `uv run python -m scripts.compile_ignores` (Markdown to stdout, or `-o FILE`).

Do not edit `scripts/ignore_sites.py`, `scripts/check_ignores.py` or the `check-ignores` hook to make a violation pass.

Exempt: `.pyi` files.
