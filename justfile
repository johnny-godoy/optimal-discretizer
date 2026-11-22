# The one entry point for people, agents and CI. Run `just` to list the recipes.
set shell := ["bash", "-euo", "pipefail", "-c"]

# List the recipes.
default:
    @just --list

# Install the locked environment and the git hooks.
sync:
    uv sync --frozen
    uv run --frozen prek install

# Run every prek hook on every file: lint, format, types, layout, design rules and the workarounds check.
check *args:
    uv run --frozen prek run --all-files {{args}}
# Fail if the change adds a copy-paste clone to src that the base revision lacks. Needs Node.js.
clones base="origin/main":
    uv run --frozen python -m scripts.check_new_clones --base {{base}}
# Run the unit tests with the 100% branch coverage gate.
test *args:
    uv run --frozen pytest {{args}}
# Run the code examples of README.md, docs/ and the docstrings with Sybil.
test-docs *args:
    uv run --frozen pytest --no-cov README.md docs src {{args}}
# Run one test, or one test file, without the coverage gate.
test-one target:
    uv run --frozen pytest --no-cov {{target}}
# Mutate the lines that changed since a base revision. CI requires zero surviving mutants.
mutate base="origin/main":
    uv run --frozen python scripts/mutation.py --base {{base}}
# Mutate every module, as the weekly workflow does.
mutate-all:
    uv run --frozen python scripts/mutation.py

# Mutate the named modules, for example `just mutate-module src/optimal_discretizer/domain/summary.py`.
mutate-module +modules:
    uv run --frozen python scripts/mutation.py $(printf -- '--module %s ' {{modules}})

# Build the docs as CI does: strict, and it fails on a docstring warning.
docs:
    uv run --frozen --group docs python -m scripts.build_docs

# Preview the docs on a local server.
docs-serve:
    uv run --frozen --group docs python -m scripts.build_docs serve

# Add a changelog fragment for a change that users can see.
changelog:
    uv run --frozen scriv create

# Check the Lean proofs. Needs elan; see proofs/README.md.
proofs:
    cd proofs && lake build
