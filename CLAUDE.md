# CLAUDE.md

<project>
optimal-discretizer: Exact 1-D k-means discretization for scikit-learn, with a Cython core.
The project comes from the Copier template modern-py. `copier update` brings the template changes, so change a
template file (a check script, a hook, a rule) in the template, not here, or the next update conflicts.
</project>

<commands>
Requirements: Python 3.14 or later for the tools (the package supports 3.11 to 3.15), `uv`, `just` and a C compiler. The `justfile` is the one entry point: CI calls the
same recipes, so a local run fails exactly when CI fails.

```bash
just                 # list the recipes
just sync            # install the locked environment and the git hooks
just check           # every prek hook: ruff, vulture, deptry, pyrefly, import-linter, semgrep, the layout and ignore checks
just test            # unit tests in tests/unit; fails below 100% branch coverage
just test-docs       # the code examples of README.md, docs/ and the docstrings, with Sybil
just test-one tests/unit/optimal_discretizer/domain/test_summary.py::test_name   # one test, without the coverage gate
just clones          # fail on a copy-paste clone that origin/main lacks; needs Node.js
just mutate          # cosmic-ray on the lines that changed since origin/main; CI requires zero survivors
just docs            # build the docs as CI does: strict, and it fails on a docstring warning
just changelog       # add a changelog fragment
just proofs          # check the Lean proofs; needs elan, see .claude/rules/proofs.md
uv run python -m scripts.check_abstractions --search error base     # find a shared contract before you add one
```
</commands>

<layout>
`src/optimal_discretizer/` follows ports and adapters. A layer imports only the layers below it:
`adapters` (I/O and vendor SDKs), `domain` (pure logic) and `core`
(errors and types). Only `adapters` imports a vendor SDK. Read `.claude/rules/architecture.md` before you add a module.
import-linter, `scripts/check_layout.py` and the semgrep rules in `semgrep/` enforce the layout, and each fails
`just check`.

The Cython kernel `domain/optimal_partition.pyx` is the one compiled module; meson-python builds it (`meson.build`).
`uv sync` installs the package as an editable install that compiles the kernel again on import. That install loads the
package through its own finder, which beartype and import-linter cannot see, so `conftest.py` and
`scripts/lint_imports.py` load the Python modules from `src` (`scripts/editable_imports.py`). The kernel is outside the
coverage and mutation tools; `tests/unit/optimal_discretizer/domain/test_clustering.py` checks it against a plain dynamic
program, and `proofs/OptimalDiscretizerProofs/KMeans1D/` models it. Change the kernel, the model and the paper together.
</layout>

<conventions>
Rules in `.claude/rules/` load automatically. Follow them, and keep these points in mind:

- Run `just check` and `just test` before you report a task as done. The hooks enforce the quality bar of the project.
- Use the libraries of `.claude/rules/libraries.md`. ruff and the layout check ban the alternatives, so a banned
  import fails at once.
- Return an attrs class, not a `dict` or a `tuple` of fields (`.claude/rules/types.md`). Semgrep enforces it.
- `beartype` checks the type hints of `optimal_discretizer` at run time, so write exact hints (`.claude/rules/types.md`).
- Search before you add a shared `Protocol`, `ABC` or cross-module helper, and register a new shared contract in
  `architecture/abstractions.yml` (`.claude/rules/reuse.md`), because a second contract for one job drifts from the first.
- The `python` code blocks of `README.md` and `docs/*.md` and the docstring `Examples` run as tests (`just test-docs`),
  so the site shows only code that works. Put setup that the reader does not need in an
  `<!-- invisible-code-block: python -->` comment.
- Give every variable, parameter and coefficient a descriptive name (`word_weight`, not `alpha`; `bin_index`, not
  `i`). See `.claude/rules/naming.md`.
- Ship each bug fix with a guard: a unit test or a semgrep rule that fails on the old code (`.claude/rules/bug-fixes.md`).
- Commit in small steps, each with one purpose and a conventional commit message (`type(scope): description`).
  Write the PR title the same way, and fill the PR template (`.claude/rules/commits-and-prs.md`). Hooks and CI check it.
- Add a changelog fragment (`just changelog`) for each user-visible change. Leave `CHANGELOG.md` and the version
  alone: the release workflow sets them after the merge (`.claude/rules/changelog-and-versioning.md`).
- Write a reason next to each `noqa`, `type: ignore`, pragma, skipped test and config ignore (` -- reason`, or a
  `# reason:` block in TOML). Fix the code or ask the user when a hook fails. Leave `scripts/check_ignores.py`,
  `scripts/ignore_sites.py` and the hook unchanged.
- Describe the code as it is now. Do not compare with an earlier version (`.claude/rules/writing-style.md`).
- Write documentation in ASD-STE100 style, and write prompts to Anthropic's prompting guide (`writing-style.md`).
- Ruff selects all rules with line length 120. Tests live in `tests/unit/optimal_discretizer/` and mirror `src/`.
- Back each exact mathematical claim ("optimal", "minimal", "exact") with a Lean proof and a Typst paper in `proofs/`,
  and keep both true when the code changes (`.claude/rules/proofs.md`).
</conventions>
