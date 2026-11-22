# scripts

Repository maintenance scripts. Run them from the repo root with `uv run python scripts/<name>.py`.

| Script | What it does |
| --- | --- |
| `check_ignores.py` | Fails unless every lint/type/coverage/test workaround has a written reason next to it. |
| `compile_ignores.py` | Compiles every workaround and its reason into one Markdown report to audit. |
| `mutation.py` | Runs cosmic-ray mutation testing in parallel shards, for all modules, some modules or only the changed lines, and fails if any mutant survives. |
| `mutant_tests.py` | Finds the tests that execute the lines of a mutant in the coverage map of `mutation.py`, so that they run first. |
| `check_changelog.py` | Fails unless `CHANGELOG.md`, the fragments in `changelog.d/` and the version in `pyproject.toml` agree. |
| `check_fragment.py` | Fails a pull request that changes the package but adds no changelog fragment. |
| `check_commits.py` | Checks the description style and the size of a commit message or of each commit of a branch. |
| `check_ruleset.py` | Fails if a required check of `.github/rulesets/main.json` is not a job that runs on every pull request. |
| `release.py` | Prints the version that the release workflow gives to the pending changelog fragments. |
| `build_docs.py` | Builds or serves the docs with Zensical (`zensical.toml`), and fails on a docstring warning. |

## `check_ignores.py` and `compile_ignores.py`

A *workaround* silences a tool instead of fixing the code:

- inline comments: `noqa`, `type: ignore`, `pyrefly: ignore`, `fmt: off`, `pragma: no cover`, `pragma: no mutate`
- `pytest.mark.skip` / `skipif` / `xfail`, and `pytest.skip()` / `xfail()`
- ignore, exclude and omit settings in `pyproject.toml` and `cosmic-ray.toml`

Each workaround carries its reason right next to it, so the reason moves with the code and cannot go stale:

```python
run(argv)  # noqa: S603 -- fixed argv from sys.executable, never untrusted input
```

```toml
# reason: recurring pattern in tests/: bare assert and literal expected values are how pytest tests are written.
"tests/**/*.py" = ["assert", "magic-value-comparison"]
```

- Python comments end in ` -- <reason>`; pytest markers and calls may pass `reason="..."` instead.
- TOML settings get a comment block directly above the key, whose first line starts with `reason:`.
- The reason must say why the code cannot be fixed, not restate what the ignore does.

`check_ignores` fails on any workaround without a reason (or with a one-word one). `compile_ignores` gathers every
workaround and its reason into one Markdown report, grouped by tool, so they can be audited in one place. The report is
generated: do not commit or edit it.

```bash
uv run python -m scripts.check_ignores                          # fails if a reason is missing
uv run python -m scripts.compile_ignores                        # report to stdout
uv run python -m scripts.compile_ignores -o ignores-report.md   # report to a file
```

`check_ignores` also runs as the `check-ignores` hook in `prek.toml`. Do not edit the scripts or the hook to make a
violation pass. The finder shared by both is `ignore_sites.py`.

## `check_exclusions.py`

`exclude-newer-package` in `pyproject.toml` lets one package skip the 7-day cutoff of uv, for example to take a security
fix at once. Such an entry is temporary. `check_exclusions` reads `uv.lock` and fails when the locked version of an
exempt package is older than the cutoff, or when the package is not locked. If it fails, delete the entry and run
`uv lock`.

```bash
uv run python -m scripts.check_exclusions   # fails if an exemption is no longer needed
```

It also runs as the `check-exclusions` hook in `prek.toml`.

## `check_changelog.py`, `check_fragment.py` and `release.py`

Each pull request with a user-visible change adds a fragment to `changelog.d/` with `just changelog`. After the
merge, `.github/workflows/release.yml` releases the fragments. `.claude/rules/changelog-and-versioning.md` has the rule.

`check_changelog` fails when:

- `CHANGELOG.md` has an `[Unreleased]` heading, or lacks the line `<!-- scriv-insert-here -->`,
- a heading is not `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD`, or the versions do not decrease from top to bottom,
- a fragment has no category, or a category that `[tool.scriv]` in `pyproject.toml` does not list,
- the version in `pyproject.toml` is lower than the newest heading, or higher with no fragment to release.

`check_fragment` compares a pull request with its base. It fails when the pull request changes `src/` and adds no
fragment. `.github/workflows/changelog.yml` runs it,
unless the pull request has the label `no-changelog`.

`release` prints the next version, or nothing if no fragment waits. A version in `pyproject.toml` above the newest
heading is a milestone version, and it is used as it is. Else, before 1.0.0, each release raises the PATCH number. From
1.0.0, the categories and the `**BREAKING:**` marks of the fragments choose the MAJOR, MINOR or PATCH number.

```bash
uv run python -m scripts.check_changelog           # fails if the changelog, the fragments and the version disagree
uv run python -m scripts.check_fragment origin/main   # fails if the branch needs a fragment
uv run python -m scripts.release                   # prints the next version
```

`check_changelog` also runs as the `check-changelog` hook in `prek.toml`.

## `check_commits.py`

`cz check` (commitizen) checks that a commit message is a conventional commit. `check_commits` checks the rest of
`.claude/rules/commits-and-prs.md`:

- the description starts with a lower-case word and has no period at the end,
- a commit changes at most 400 lines without generated files (`uv.lock`, `CHANGELOG.md`, `changelog.d/`), unless its
  message has the trailer `Large-Commit: <reason of at least 4 words>`.

Merge commits and `fixup!` or `squash!` commits are skipped.

```bash
uv run python -m scripts.check_commits --message-file .git/COMMIT_EDITMSG   # one message, as the commit-msg hook does
uv run python -m scripts.check_commits --base origin/main                   # each commit of the branch, as CI does
```

The `commit-style` hook in `prek.toml` runs it at the `commit-msg` stage, next to the `commitizen` hook.
`.github/workflows/commits.yml` runs both on the title and the commits of each pull request.

## `check_ruleset.py`

`.github/rulesets/main.json` lists the checks that a pull request must pass. GitHub matches each one by the name of a
job. If no job of that name runs on every pull request, the check never reports, and every pull request waits for it.
`check_ruleset` fails when a required check:

- is not the name of a job in a workflow that runs on `pull_request`,
- belongs to a workflow with a `paths` or `paths-ignore` filter on `pull_request`,
- is the name of more than one job that runs on `pull_request`.

```bash
uv run python -m scripts.check_ruleset   # fails if a required check cannot report
```

It also runs as the `check-ruleset` hook in `prek.toml`. `.github/rulesets/README.md` says how to apply the ruleset.

## `build_docs.py`

`build` is the default command. It runs `zensical build --strict`, and it fails if the output has a `griffe:` warning.
CI runs the same command. `serve` starts the preview server. The module docstring says what the build exports first.

```bash
uv run --group docs python -m scripts.build_docs [build|serve]
```

## `mutation.py`

cosmic-ray mutates the source tree in place, so each shard works on its own copy of `src`, `tests`, `pyproject.toml`
and `cosmic-ray.toml`. The script:

1. creates a session in `.mutation/session.sqlite` and drops mutants on `# pragma: no mutate` lines,
2. if you give `--base`, drops the mutants that touch no line changed since that revision; if you give `--module`,
   drops the mutants of all other modules,
3. runs the test baseline with one coverage context for each test, and stops if a test fails,
4. splits the work items of each module over the shards and runs them concurrently,
5. prints a progress line every minute, with the finished, surviving and remaining mutants,
6. merges the results back and prints the survival rate.

The baseline writes a coverage map: the tests that execute each line of the mutated modules (`mutant_tests.py`).
Under a mutant, each shard runs the tests that execute the mutated statements first, then the other tests of the
mutated module, then the rest (`tests/unit/conftest.py` reads `MUTATION_FIRST`, `MUTATION_MODULE`,
`MUTATION_ORIGINAL` and `MUTATION_COVERAGE`). The run stops at the first failure, so a killed mutant runs only a few
tests, and a surviving mutant runs all of them. Without the variables, the tests run in the normal order.

```bash
uv run python scripts/mutation.py      # one shard per CPU
uv run python scripts/mutation.py 4    # four shards
uv run python scripts/mutation.py --base origin/main   # only the lines changed since main
uv run python scripts/mutation.py --module src/optimal_discretizer/domain/summary.py   # only one module
```

If no module changed, the script exits with code 0 and runs nothing. The PR run in CI uses `--base`. The workflow
`mutation-weekly.yml` runs all modules each Monday, and only if code changed in the last 7 days. It starts one job for
each module with `--module`, and opens one issue that lists the surviving mutants of all jobs.

Exits non-zero if any mutant survives. CI requires a 100% mutation score. Settings (module path, timeout, test command)
are in `cosmic-ray.toml`. `just mutate`, `just mutate-all` and `just mutate-module` call the script.
