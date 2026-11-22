<!--
Title: a conventional commit, for example "feat(domain): add the median to the summary". Use a lower-case description with
no period, at most 72 characters. A squash merge makes the title the commit on main.
.claude/rules/commits-and-prs.md has the rules.
-->

## Summary

<!-- What changes for users or contributors, and why. Two to five sentences. -->

## Changes

<!-- One line for each commit or group of commits. Each commit has one purpose. -->

-

## Abstraction reuse

<!-- Answer for a change that adds a shared Protocol, ABC, service, adapter or cross-module helper. Write "None" for any
other change. A reviewer judges the reasons. CI checks only the registry and the clones. -->

- New shared abstraction? [ ] No [ ] Yes
- Existing candidates inspected (`uv run python -m scripts.check_abstractions --search <words>`):
- Capability ID and owner in `architecture/abstractions.yml` (if new):
- Why the existing abstractions cannot be reused:

## Changelog

<!-- Choose one. -->

- [ ] This PR adds a fragment in `changelog.d/` (`just changelog`).
- [ ] Users see no change. The PR has the label `no-changelog`, or it changes no file in `src/`.

## Breaking changes

<!-- "None", or what breaks and what users must change. Mark the fragment entry with **BREAKING:**. -->

None.

## Roadmap

<!-- The milestone and the plan in docs/plans/ that this PR works on, or "None". A PR that completes a milestone sets
its version in pyproject.toml and its status in ROADMAP.md. -->

None.

## Checks

<!-- Tick what you ran. Say why for each check that you could not run. -->

- [ ] `just check`
- [ ] `just clones` (if `src/` changed; needs `origin/main` and Node.js)
- [ ] `just test` (100% coverage)
- [ ] `just test-docs` (the documentation examples)
- [ ] `just mutate` (if `src/` changed)
- [ ] `just docs` (if the docs changed)
- [ ] `just proofs` (if `proofs/` or code that a proof covers changed)
