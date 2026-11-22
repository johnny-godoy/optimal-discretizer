"""Tests for the check that each required status check of the ruleset can report on every pull request."""

from pathlib import Path
from typing import Any

import orjson
import pytest
import yaml
from scripts import check_ruleset

CI: dict[Any, Any] = {
    True: {"push": {"branches": ["main"]}, "pull_request": None},
    "jobs": {"prek": {}, "py": {"name": "pytest"}},
}
PROOFS: dict[Any, Any] = {True: {"pull_request": {"paths": ["proofs/**"]}}, "jobs": {"lake": {"name": "lake build"}}}
RELEASE: dict[Any, Any] = {True: {"push": {"branches": ["main"]}}, "jobs": {"build": {}}}


def ruleset(*names: str) -> dict[str, Any]:
    checks = [{"context": name, "integration_id": 15368} for name in names]
    return {
        "rules": [
            {"type": "deletion"},
            {"type": "required_status_checks", "parameters": {"required_status_checks": checks}},
        ],
    }


def test_required_checks_reads_the_contexts() -> None:
    assert check_ruleset.required_checks(ruleset("prek", "pytest")) == ["prek", "pytest"]


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        ("pull_request", {}),
        (["push", "pull_request"], {}),
        ({"pull_request": None}, {}),
        ({"pull_request": {"types": ["edited"]}}, {"types": ["edited"]}),
        ("push", None),
        (["push"], None),
        ({"push": None}, None),
    ],
)
def test_pull_request_trigger_reads_every_form_of_on(on: object, expected: dict[str, Any] | None) -> None:
    assert check_ruleset.pull_request_trigger({True: on, "jobs": {}}) == expected


def test_job_names_use_the_name_or_the_id() -> None:
    assert check_ruleset.job_names(CI) == ["prek", "pytest"]


def test_checks_of_jobs_that_run_on_every_pull_request_pass() -> None:
    assert check_ruleset.ruleset_problems(["prek", "pytest"], {"ci.yml": CI, "release.yml": RELEASE}) == []


def test_a_check_that_no_job_reports_fails() -> None:
    [problem] = check_ruleset.ruleset_problems(["build"], {"ci.yml": CI, "release.yml": RELEASE})
    assert problem == "required check 'build' is not the name of a job that runs on pull_request"


def test_a_check_of_a_path_filtered_workflow_fails() -> None:
    [problem] = check_ruleset.ruleset_problems(["lake build"], {"proofs.yml": PROOFS})
    assert problem.startswith("required check 'lake build' runs only for some paths (proofs.yml)")


def test_a_check_with_two_jobs_of_the_same_name_fails() -> None:
    other: dict[Any, Any] = {True: {"pull_request": None}, "jobs": {"x": {"name": "prek"}}}
    [problem] = check_ruleset.ruleset_problems(["prek"], {"ci.yml": CI, "other.yml": other})
    assert problem == "required check 'prek' is the name of 2 jobs: rename them"


def test_main_checks_the_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "main.json").write_bytes(orjson.dumps(ruleset("prek", "docs build")))
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "ci.yml").write_text(yaml.safe_dump({"on": {"pull_request": None}, "jobs": {"prek": {}}}))
    monkeypatch.setattr(check_ruleset, "RULESET", tmp_path / "main.json")
    monkeypatch.setattr(check_ruleset, "WORKFLOWS", tmp_path / "workflows")
    assert check_ruleset.main() == 1
    assert "'docs build' is not the name of a job" in capsys.readouterr().err
    (tmp_path / "main.json").write_bytes(orjson.dumps(ruleset("prek")))
    assert check_ruleset.main() == 0


def test_the_ruleset_of_the_repository_matches_its_workflows() -> None:
    assert check_ruleset.main() == 0
