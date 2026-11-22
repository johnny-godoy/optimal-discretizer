"""Fail when a required status check of the ruleset of ``main`` cannot report on a pull request.

``.github/rulesets/main.json`` lists the checks that a pull request must pass before it merges. GitHub matches each
required check by the name of a job. If no job of that name runs on every pull request, the check never reports, and
every pull request waits for it forever. This check fails when a required name:

- is not the name of a job in a workflow that runs on ``pull_request``,
- belongs to a workflow that runs on ``pull_request`` only for some paths, so the job does not run on every pull
  request,
- belongs to more than one job that runs on ``pull_request``, so a pass of one job hides a failure of the other.

Run it from the repo root: ``uv run python -m scripts.check_ruleset``.
"""

import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import orjson
import yaml

ROOT = Path(__file__).resolve().parent.parent
RULESET = ROOT / ".github" / "rulesets" / "main.json"
WORKFLOWS = ROOT / ".github" / "workflows"
PATH_FILTERS = ("paths", "paths-ignore")


def required_checks(ruleset: Mapping[str, Any]) -> list[str]:
    """List the names of the required status checks of a ruleset.

    Parameters
    ----------
    ruleset: Mapping[str, Any]
        The parsed ruleset, in the JSON form of the GitHub rulesets API.

    Returns
    -------
    list[str]
        The ``context`` of each required status check.

    """
    names: list[str] = []
    for rule in ruleset["rules"]:
        if rule["type"] == "required_status_checks":
            names += [check["context"] for check in rule["parameters"]["required_status_checks"]]
    return names


def pull_request_trigger(workflow: Mapping[Any, Any]) -> dict[str, Any] | None:
    """Read the settings of the ``pull_request`` trigger of a workflow.

    Parameters
    ----------
    workflow: Mapping[Any, Any]
        The parsed workflow file. PyYAML reads the key ``on`` as the boolean ``True``.

    Returns
    -------
    dict[str, Any] | None
        The settings of the trigger (empty if it has none), or ``None`` if the workflow does not run on
        ``pull_request``.

    """
    triggers: Any = workflow.get("on", workflow.get(True))
    if isinstance(triggers, str):
        triggers = [triggers]
    if isinstance(triggers, list):
        return {} if "pull_request" in triggers else None
    if not isinstance(triggers, dict) or "pull_request" not in triggers:
        return None
    return dict(triggers["pull_request"] or {})


def job_names(workflow: Mapping[Any, Any]) -> list[str]:
    """List the names of the jobs of a workflow, as GitHub names their checks.

    Parameters
    ----------
    workflow: Mapping[Any, Any]
        The parsed workflow file.

    Returns
    -------
    list[str]
        The ``name`` of each job, or its id if it has no ``name``.

    """
    jobs: dict[str, Any] = workflow["jobs"]
    return [str(job.get("name", job_id)) for job_id, job in jobs.items()]


def ruleset_problems(required: Iterable[str], workflows: Mapping[str, Mapping[Any, Any]]) -> list[str]:
    """List the required checks that cannot report on every pull request.

    Parameters
    ----------
    required: Iterable[str]
        The names of the required status checks.
    workflows: Mapping[str, Mapping[Any, Any]]
        The parsed workflows, by file name.

    Returns
    -------
    list[str]
        One message for each problem.

    """
    every_pull_request: Counter[str] = Counter()
    some_pull_requests: dict[str, str] = {}
    for file_name, workflow in workflows.items():
        trigger = pull_request_trigger(workflow)
        if trigger is None:
            continue
        filtered = any(key in trigger for key in PATH_FILTERS)
        for name in job_names(workflow):
            if filtered:
                some_pull_requests[name] = file_name
            else:
                every_pull_request[name] += 1
    problems = []
    for name in required:
        if name in some_pull_requests:
            problems.append(
                f"required check '{name}' runs only for some paths ({some_pull_requests[name]}), so it never reports "
                "on the other pull requests",
            )
        elif every_pull_request[name] == 0:
            problems.append(f"required check '{name}' is not the name of a job that runs on pull_request")
        elif every_pull_request[name] > 1:
            problems.append(f"required check '{name}' is the name of {every_pull_request[name]} jobs: rename them")
    return problems


def main() -> int:
    """Report every required check that cannot report on every pull request.

    Returns
    -------
    int
        The process exit code: 0 if every required check can report, 1 otherwise.

    """
    ruleset = orjson.loads(RULESET.read_bytes())
    workflows = {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(WORKFLOWS.glob("*.yml"))
    }
    problems = ruleset_problems(required_checks(ruleset), workflows)
    for problem in problems:
        sys.stderr.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
