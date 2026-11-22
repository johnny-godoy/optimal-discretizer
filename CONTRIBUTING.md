# Contributing

1. Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/). Then run `just sync`. The recipe
   installs the environment and the hooks that check each commit and its message.
2. Make your change with tests. Run `just check` and `just test`, and fix every failure. Do not bypass the hooks.
3. If a function has an invariant, write a Hypothesis property test for it. CI loads the `ci` profile (see
   `tests/unit/conftest.py`), so CI draws the same examples every time. If a property finds a bug, keep the failing
   example as a separate regression test.
4. A workaround (`# noqa`, `# type: ignore`, `pytest.mark.skip`, ...) needs a written reason next to it. Check with
   `uv run python -m scripts.check_ignores`.
5. For a user-visible change, run `just changelog` and write the entries in the new file in `changelog.d/` (see
   `changelog.d/README.md`). Do not edit `CHANGELOG.md` or the version: the release workflow sets them after the merge.
   If the change is internal but touches `src/`, add the label `no-changelog`.
6. Commit in small steps. Give each commit one purpose and a conventional commit message, for example
   `fix(domain): reject an empty sequence`. `.claude/rules/commits-and-prs.md` has the rules.
7. Open a pull request with a conventional commit title, and fill the template. CI must pass.

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
