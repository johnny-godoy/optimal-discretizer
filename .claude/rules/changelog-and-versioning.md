# Changelog and versioning

## Add a changelog fragment, and let the release workflow release it

Every merge to `main` reaches the users of the repository, so each merge with a user-visible change is released at
once. Agents forgot to raise the version and left changes under `[Unreleased]`, so the version did not say what users
had. A fragment per pull request and a release workflow after the merge make the release automatic, and two open pull
requests never conflict on the version or the changelog.

- In a PR with a user-visible change, run `just changelog`, uncomment the right category sections of the new file
  in `changelog.d/`, and write the entries there. Commit the fragment with the change. `changelog.d/README.md` has the
  steps.
- Mark a breaking change with `**BREAKING:**` at the start of its entry, or put it under `Removed`.
- Do not edit `CHANGELOG.md` or `version` in `pyproject.toml`. After the merge, `.github/workflows/release.yml` chooses
  the version (`scripts/release.py`), runs `uv version`, moves the fragments into `CHANGELOG.md` with `scriv collect`,
  and pushes the release commit and the tag `vX.Y.Z`. It then creates the GitHub release of the tag, with the
  `CHANGELOG.md` entry as notes (`scriv print`) and the built files. Do not push tags or create releases by hand.
- The one exception: the PR that completes a milestone of `ROADMAP.md` also sets `version` in `pyproject.toml` to the
  milestone version (for example 0.1.0) and runs `uv lock`. The release workflow then uses that version.
- A PR with no user-visible change (tests, CI, hooks, contributor docs, plans, an internal refactor) gets no fragment.
  If it changes `src/`, add the label `no-changelog` to the PR.
- Guards: the `check-changelog` hook (`scripts/check_changelog.py`) checks the fragments, the headings and the
  version. `.github/workflows/changelog.yml` (`scripts/check_fragment.py`) fails a PR that changes those paths with no
  fragment and no `no-changelog` label.

## Semantic versioning

The project follows [Semantic Versioning 2.0.0](https://semver.org/) strictly. The single source of truth is `version`
in `pyproject.toml`. `ROADMAP.md` lists the planned versions.

| Version range | Breaking change | New feature | Fix, docs, internal change |
| --- | --- | --- | --- |
| Before 1.0.0 | PATCH, marked **BREAKING** | PATCH | PATCH |
| From 1.0.0 | MAJOR, after a deprecation in a MINOR | MINOR | PATCH |

- Before 1.0.0, the PR that completes a milestone of `ROADMAP.md` takes the MINOR version of that milestone (for
  example 0.1.0) instead of a PATCH. The roadmap then decides the MINOR numbers, and the PRs between milestones do not
  use them up.
- The public API is the public Python names. Log events and the text of error messages are not part of it.
- `optimal_discretizer.experimental` is outside the public API. It can change in a MINOR or PATCH at any time. Say so in
  its docstrings. The layout check accepts layers only, so add `experimental` to the layers contract and to
  `architecture.md` with its first feature.
- From 1.0.0, deprecate before you remove: keep the old name for at least one MINOR with a `DeprecationWarning`, and add
  a `Deprecated` entry. Remove it only in the next MAJOR.
- Never invent a version. `scripts/release.py` derives it from the table above, and a milestone PR takes it from
  `ROADMAP.md`.

## Changelog

- Keep `CHANGELOG.md` at the repo root in [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) format, with
  no `[Unreleased]` section: the pending entries are the fragments in `changelog.d/`. scriv inserts each release below
  the line `<!-- scriv-insert-here -->`.
- Group entries under: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Omit empty groups.
- Write entries for users, not for the diff: say what changed and why it matters, one line each. Skip pure internal churn (formatting, test-only edits, CI tweaks).
- The changelog is for people who use the package: public API changes, behavior changes, bug fixes and dependency
  changes that affect them. Leave out repository metadata and developer tooling (`CITATION.cff`, `dependabot.yml`, issue and PR templates, CI workflows, test suites, prek hooks, contributor docs, `ROADMAP.md`, `docs/plans/`), even when the change is new.
- scriv writes no compare links at the bottom of the file. Do not add them by hand.
