# Changelog fragments

Each pull request with a user-visible change adds one fragment to this directory. After the merge, the release workflow
gives the fragments a version and moves them into `CHANGELOG.md`.

1. Run `just changelog`. The recipe writes a new file here from a template.
2. Uncomment the section of each category that applies: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` or
   `Security`.
3. Write one line for each change, for the users of the package.
4. Mark a breaking change with `**BREAKING:**` at the start of its line.
5. Commit the fragment with the change.

Do not edit `CHANGELOG.md` or the version in `pyproject.toml`. The release workflow changes them. A pull request that
completes a milestone of `ROADMAP.md` is the only exception: it sets the version of the milestone in `pyproject.toml`.

`uv run python -m scripts.check_changelog` checks the fragments. `.claude/rules/changelog-and-versioning.md` has the
full rule.
