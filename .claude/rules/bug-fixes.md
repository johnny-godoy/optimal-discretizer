# Bug fixes need a guard

Every bug fix ships with a guard that fails if the bug comes back. A fix without a guard leaves the bug free to return
unseen, because nobody remembers the cause later.

## Choose the guard

| The bug is | Guard |
| --- | --- |
| Wrong behavior of one function for some input | A unit test in the mirrored test file that fails on the old code. |
| A code pattern that is wrong wherever it appears (for example `**kwargs` bags, I/O in domain code) | A semgrep rule in `semgrep/rules.yml`, with a `ruleid` and an `ok` line in `semgrep/rules.py`. |
| A wrong import across layers | A contract in `[tool.importlinter]` in `pyproject.toml`. See `architecture.md`. |

- Prefer a unit test when the bug depends on values. Prefer a semgrep rule when the bug is a pattern that could appear
  in other places.
- Write the guard first and watch it fail on the unfixed code. Then fix the bug and watch the guard pass. A guard that
  never failed may test nothing.
- Name the bug in the guard. A test name such as `test_empty_task_has_zero_accuracy`, or the rule message, tells the next
  reader why the guard exists.
- Put the guard in the same commit or PR as the fix, and add the user-visible fix to a changelog fragment under `Fixed`.
- If no guard is possible, write the reason in the PR description. Do not skip the guard because the fix is small.
