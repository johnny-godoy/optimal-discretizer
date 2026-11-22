# Rulesets

`main.json` is the ruleset of the default branch, in the JSON form of the
[GitHub rulesets API](https://docs.github.com/en/rest/repos/rules). The file is the source of truth. GitHub does not
read it by itself, so a maintainer applies each change.

## Rules

| Rule | Effect |
| --- | --- |
| `deletion`, `non_fast_forward` | Nobody can delete `main` or force-push to it. |
| `pull_request` | A change reaches `main` only through a pull request, after every review thread is resolved. |
| `allowed_merge_methods: ["rebase"]`, `required_linear_history` | A pull request merges by rebase. Its atomic commits reach `main` one by one, so `git bisect` and `git revert` can use them. |
| `required_status_checks` | A pull request merges only when the CI gates, the docs build and the `Changelog` and `Commits` checks pass. |

`integration_id` 15368 is the GitHub Actions app. A check of the same name from another app does not count.

The pull requests need no approval (`required_approving_review_count: 0`), because the project has one maintainer.
Raise the count with `copier update --data required_approvals=<n>` when the project has more reviewers.

## Bypass

A repository admin (`RepositoryRole` 5) can bypass the ruleset at any time. The release workflow needs the bypass: it
pushes the release commit to `main` without a pull request. Give the workflow a token of an admin:

1. Create a fine-grained personal access token with the permission `Contents: Read and write` on this repository.
2. Add it as the repository secret `RELEASE_TOKEN`.

## Apply a change

The `check-ruleset` hook (`scripts/check_ruleset.py`) checks that each required check is the name of a job that runs
on every pull request. A required check that never reports blocks every pull request, so run the hook first.

1. Run `uv run python -m scripts.check_ruleset`.
2. If the repository has no ruleset with the name `main`, create it:

   ```bash
   gh api --method POST repos/johnny-godoy/optimal-discretizer/rulesets --input .github/rulesets/main.json
   ```

3. Else, find its id and update it:

   ```bash
   id=$(gh api repos/johnny-godoy/optimal-discretizer/rulesets --jq '.[] | select(.name == "main") | .id')
   gh api --method PUT "repos/johnny-godoy/optimal-discretizer/rulesets/$id" --input .github/rulesets/main.json
   ```

If you rename a job that the ruleset requires, change `main.json` in the same pull request, and apply it after the
merge.
