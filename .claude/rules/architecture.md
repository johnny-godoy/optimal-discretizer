# Architecture and guards

The layout of `src/optimal_discretizer/` makes the SOLID rules (`solid.md`) checkable. It follows ports and adapters:
the domain in the middle knows nothing about I/O, and the adapters at the edge connect it to the world. Tools enforce
the limits below, so a change that breaks one fails `just check`. Put new code where the layer rules say.

## Layers

| Package | Job | May import |
| --- | --- | --- |
| `optimal_discretizer.adapters` | The edge: the scikit-learn estimator, and any file, network or vendor SDK. | `domain`, `core` |
| `optimal_discretizer.domain` | Pure logic: functions of their arguments, with attrs classes as the types. | `core` |
| `optimal_discretizer.core` | Shared kernel: errors and types. | No other `optimal_discretizer` package. |

- Only `adapters` imports a vendor SDK. The reason: domain code then runs in a plain unit test (SOLID: D), and a
  change of vendor stays in one layer. import-linter checks the SDKs that the project has, and the list grows with
  each new SDK in the contract "Only the adapters import the vendor SDKs".
- Search for an existing contract before you add a shared one (`reuse.md`), and register a new shared contract in
  `architecture/abstractions.yml`.
- A lower layer never imports a higher one. If `domain` needs a service (a clock, a store), take it as a `Callable`
  or `Protocol` parameter and let the caller pass the real one.
- Add a new feature as a new module in the layer that fits. Add a new layer only with a new entry in the import-linter
  layers contract and a new row in this table.
- Give each module a name that no other module in `src/optimal_discretizer` has. `scripts/mutation.py` finds the tests
  of a module by its name.
- Mirror the source tree in the test tree. Put the test of `src/optimal_discretizer/<layer>/<name>.py` in
  `tests/unit/optimal_discretizer/<layer>/test_<name>.py`. A test file or directory with no source at the mirrored path
  is an error.

## Guards

Each guard checks one kind of rule. Run all of them with `just check`.

| Guard | Config | What it checks |
| --- | --- | --- |
| import-linter | `[tool.importlinter]` in `pyproject.toml` | The layer order and the vendor SDK limits. Run it alone with `uv run lint-imports`. |
| Layout check | `scripts/check_layout.py` | Where files live: layers only, a docstring in each `__init__.py`, unique module names, a mirrored test tree, and the banned files. |
| semgrep | `semgrep/rules.yml` | Code patterns that mean a design problem: `**kwargs` bags, `elif` chains on one value, `NotImplementedError` stubs, I/O in domain code, a bare `raise ValueError`, a container where an attrs class belongs, an `object` type hint, an `isinstance` check of a concrete container, branches on the type of one value, `attrs.asdict` without `recurse=False` in a `**` call. |
| ruff `banned-api` | `[tool.ruff.lint.flake8-tidy-imports.banned-api]` in `pyproject.toml` | The imports of the libraries that `libraries.md` replaces. |
| Abstraction registry | `architecture/abstractions.yml`, `scripts/check_abstractions.py` | One owner and one canonical symbol for each shared capability: unique IDs, symbols that exist, no second claim on a symbol or a responsibility. `reuse.md` has the process. |
| Contract overlap | `scripts/check_contract_overlap.py` | Public `Protocol` and `ABC` classes with identical signatures in one context. |
| New clones | `scripts/check_new_clones.py` | A copy-paste clone in `src/optimal_discretizer` that the base branch lacks. CI runs it on each pull request, and `just clones` runs it locally. |
| Claude rules | `.claude/rules/` | The design judgment that no tool can check: one job per unit, small interfaces. |

- Fix the code when a guard fails. Do not add an exception to a guard to make it pass.
- Give each new semgrep rule a test in `semgrep/rules.py`, with one line that must match and one that must not. Run
  `uv run semgrep --test semgrep`.
- Add a new import limit as a contract in `pyproject.toml`, not as a semgrep rule, because import-linter sees the
  whole import graph.
