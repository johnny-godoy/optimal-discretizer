# Commits and pull requests

A reviewer reads the history one commit at a time, and `git bisect` and `git revert` work on whole commits. So each
commit has one purpose and a message that says it in a fixed form. Agents tend to put a whole task in one large commit,
which no reviewer can read and no revert can take apart.

## Conventional commits

Write each commit message as a [conventional commit](https://www.conventionalcommits.org/en/v1.0.0/):

```text
type(scope)!: description

Body: why the change is needed, and what a reviewer must know. Wrap it at 72 characters.

BREAKING CHANGE: what breaks, and what users must change.
```

| Type | Use it for |
| --- | --- |
| `feat` | A new behavior that users can use. |
| `fix` | A bug fix. |
| `perf` | A faster or smaller version of the same behavior. |
| `refactor` | A change of structure with no change of behavior. |
| `docs` | Documentation, docstrings, plans and rules only. |
| `test` | Tests only. |
| `build` | Dependencies, packaging, prek hooks and the tools that they run. |
| `ci` | Workflows and CI scripts. |
| `style` | Formatting only. |
| `chore` | Other maintenance, such as the release commit of the release workflow. |
| `revert` | A revert of an earlier commit. |

- Use a scope when the change is in one area: `adapters`, `domain`, `core`, `docs`, `proofs` or
  `deps`.
- Write the description in the imperative ("add", not "added" or "adds"), start it with a lower-case word, and end it
  with no period. Keep the first line at 72 characters or fewer.
- Mark a breaking change with `!` after the type or scope, and explain it in a `BREAKING CHANGE:` footer. Also mark its
  changelog fragment with `**BREAKING:**`, because the fragments, not the commit types, decide the version
  (`changelog-and-versioning.md`).

## Atomic commits

- Give each commit one purpose. If the description needs "and", split the commit.
- Put the tests of a change in the same commit as the change. A bug fix commit holds its guard (`bug-fixes.md`).
- Keep a refactor apart from a change of behavior, and a mechanical change (formatting, a rename, a move) apart from an
  edit. The reviewer then reads the edit without the noise.
- Commit a generated file with its source: `uv.lock` with `pyproject.toml`, the changelog fragment with its change.
- Make each commit pass `prek run --all-files` and `uv run pytest`, so that `git bisect` can test any commit.
- Keep a commit at 400 changed lines or fewer, without generated files. If one purpose needs more (a file move, a
  generated fixture), add the trailer `Large-Commit: <reason>` with a reason of at least 4 words.
- Commit each step when it passes, not the whole task at the end. If the working tree holds several changes, stage each
  one by its paths (`git add <paths>`). `git add -p` is interactive, so it is not available to an agent.

## Pull requests

- Give each pull request one topic. A second topic is a second pull request.
- Write the title as a conventional commit, with the same rules as a commit message. The ruleset of `main` allows rebase
  merges only, so the commits reach `main` as they are. The title names the pull request in the history of GitHub, and
  it becomes the commit if the merge method changes to squash.
- Fill every section of `.github/pull_request_template.md`. Say why for each check that you could not run.

## Guards

- `prek install` installs a `commit-msg` hook: `cz check` (commitizen) checks the conventional commit form, and
  `scripts/check_commits.py --message-file` checks the style of the description. The `SessionStart` hook in
  `.claude/settings.json` runs `prek install` in each Claude Code session.
- `.github/workflows/commits.yml` checks the title and each commit of a pull request, with the same tools and the size
  limit (`scripts/check_commits.py --base`).
- Dependabot writes `build(deps): ...` and `ci(deps): ...` messages (`.github/dependabot.yml`).
- `.github/rulesets/main.json` makes the CI gates, the docs build and the `Changelog` and `Commits` checks required on
  `main`. The `check-ruleset` hook (`scripts/check_ruleset.py`) fails if a required check is not the name of a job that
  runs on every pull request. If you rename such a job, change the ruleset in the same pull request.
- Do not bypass a hook with `--no-verify`.
