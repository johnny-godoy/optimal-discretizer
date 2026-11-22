# optimal-discretizer

<!-- --8<-- [start:intro] -->
Exact 1-D k-means discretization for scikit-learn, with a Cython core.
<!-- --8<-- [end:intro] -->

## Install

<!-- --8<-- [start:install] -->
```bash
uv add optimal-discretizer
```
<!-- --8<-- [end:install] -->

## Development

<!-- --8<-- [start:development] -->
Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/). Then run `just sync` to install the
environment and the git hooks. `just` lists every recipe.

| Recipe | What it does |
| --- | --- |
| `just check` | Runs every prek hook on every file. |
| `just clones` | Fails on a copy-paste clone that `origin/main` lacks. |
| `just test` | Runs the unit tests with the 100% branch coverage gate. |
| `just test-docs` | Runs the code examples of the docs and the docstrings. |
| `just test-one <test>` | Runs one test without the coverage gate. |
| `just mutate` | Runs mutation testing on the lines that changed since `origin/main`. |
| `just docs` | Builds the docs as CI does. |
| `just changelog` | Adds a changelog fragment. |
| `just proofs` | Checks the Lean proofs. |

`CONTRIBUTING.md` has the rules for changes, commits and pull requests.
<!-- --8<-- [end:development] -->

## Release

<!-- --8<-- [start:release] -->
After each merge to `main`, the release workflow gives the changelog fragments a version, tags it and creates the
GitHub release. It also uploads the package to PyPI with trusted publishing. Do these steps once:

1. On PyPI, add a trusted publisher for `johnny-godoy/optimal-discretizer`, the workflow `release.yml` and the
   environment `pypi`.
2. On GitHub, create the environment `pypi`, and set the repository variable `PUBLISH_TO_PYPI` to `true`.
<!-- --8<-- [end:release] -->
