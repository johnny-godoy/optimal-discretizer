#!/usr/bin/env python3
"""Turn raw CI tool output into short, actionable failure reports.

Four subcommands, all stdlib only:

``snippet <gate>``
    Run inside a failed job. Reads that gate's logs from ``$CI_LOGS`` and writes ``$CI_REPORT/<gate>.md`` holding
    exactly what failed and how to fix it. Also emits ``::error`` annotations so findings show on the diff.

``assemble``
    Run in the final job. Combines every snippet with the job results in ``$NEEDS`` (``toJSON(needs)``) into one
    markdown report: written to ``$CI_REPORT/comment.md`` and the step summary.

``watch``
    Run in the ``progress`` job, next to the gates. Every ``POLL_SECONDS`` seconds it reads the state of the gate jobs
    from the GitHub API and updates the PR comment ("CI in progress"), until all gates have finished.

``post <file>``
    Create the PR comment from a file, or replace it if it exists. The ``report`` job uses it for the final report.
    ``watch`` and ``post`` find the comment by ``MARKER``, so one comment changes during the whole run. Without write
    access (a fork PR) they do nothing.
"""

import json  # ruff: ignore[banned-api] -- runs under the bare python3 of the runner, with no project environment
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

LOGS: Path = Path(os.environ.get("CI_LOGS", Path(tempfile.gettempdir()) / "ci-logs"))
REPORT: Path = Path(os.environ.get("CI_REPORT", Path(tempfile.gettempdir()) / "ci-report"))
MAX_CHARS = 6000
MAX_LOG_TAIL = 3000
PERCENT = 100
SNIPPET_ARGC = 3
POST_ARGC = 3
POLL_SECONDS = 20
WATCH_LIMIT_SECONDS = 70 * 60
PAGE_SIZE = 100
FORBIDDEN = (401, 403)
MARKER = "<!-- ci-report -->"
FINISHED = frozenset({"success", "failure", "cancelled", "skipped"})

# (job id, title) in fail-fast order.
GATES = [
    ("prek", "prek hooks"),
    ("trufflehog", "trufflehog (secrets)"),
    ("semgrep", "semgrep (base rules)"),
    ("trivy", "trivy (vulnerabilities, secrets, misconfig)"),
    ("pytest", "pytest + 100% coverage"),
    ("mutation", "mutation score 100%"),
]

PREK_HINTS = {
    "ruff-format": "Formatter rewrote files. Commit the changes: `uvx prek run ruff-format --all-files`.",
    "ruff-check": "Fix the lint errors (autofixes were applied, commit them): `uvx prek run ruff-check --all-files`.",
    "vulture": "Dead code. Delete it, or use it. Check locally: `uvx prek run vulture --all-files`.",
    "pyrefly": "Type errors. Fix them. Check locally: `uvx prek run pyrefly --all-files`.",
    "pyrefly-coverage": (
        "A name has no type annotation. Annotate it. List them: "
        "`uv run pyrefly coverage check src tests scripts .github/scripts`."
    ),
    "actionlint": (
        "Workflow syntax error. Fix the file named above. Check locally: `uvx prek run actionlint --all-files`."
    ),
}
PREK_DEFAULT_HINT = (
    "Reproduce locally with `uvx prek run --all-files`. Hooks that modify files: commit what they changed."
)


def read(path: Path) -> str:
    """Read a log file, tolerating a missing file and undecodable bytes.

    Parameters
    ----------
    path: Path
        The file to read.

    Returns
    -------
    str
        The contents of the file, or an empty string if it does not exist.

    """
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def clip(text: str, limit: int = MAX_CHARS) -> str:
    """Truncate a text to a number of characters.

    Parameters
    ----------
    text: str
        The text to truncate.
    limit: int
        The maximum number of characters kept.

    Returns
    -------
    str
        The text, with a note on the dropped characters if it was truncated.

    """
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n... [{len(text) - limit} more characters, see the job log]"


def block(text: str) -> str:
    """Wrap a text in a markdown code fence.

    Parameters
    ----------
    text: str
        The text to wrap.

    Returns
    -------
    str
        The fenced, clipped text.

    """
    return f"```\n{clip(text)}\n```"


def annotate(file: str, line: int | str, message: str) -> None:
    """Emit a GitHub ``::error`` annotation, so that a finding shows on the diff.

    Parameters
    ----------
    file: str
        The file of the finding.
    line: int | str
        The line of the finding.
    message: str
        The text of the annotation.

    """
    message = message.replace("\n", " ").replace("%", "%25")
    sys.stdout.write(f"::error file={file},line={line}::{message}\n")


def prek() -> str:
    """Report the prek hooks that failed.

    Returns
    -------
    str
        The markdown with the failure and how to fix it.

    """
    log = read(LOGS / "prek.log")
    failed: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in log.splitlines():
        status = re.match(r"^(.+?)\.{3,}\s*(Passed|Failed|Skipped)", line)
        if status:
            current = [] if status.group(2) == "Failed" else None
            if current is not None:
                failed.append((status.group(1).strip(), current))
        elif current is not None:
            current.append(line)
    if not failed:
        return f"No hook result was parsed. Last output:\n{block(log[-MAX_LOG_TAIL:])}\n\n**Fix:** {PREK_DEFAULT_HINT}"
    parts = []
    for name, output in failed:
        hook_id = next((m.group(1) for ln in output if (m := re.match(r"^- hook id: (\S+)", ln))), name)
        hint = PREK_HINTS.get(hook_id, PREK_DEFAULT_HINT)
        parts.append(f"**Hook `{name}` failed**\n{block(chr(10).join(output))}\n**Fix:** {hint}")
    return "\n\n".join(parts)


def trufflehog() -> str:
    """Report the secrets that trufflehog found.

    Returns
    -------
    str
        The markdown with the failure and how to fix it.

    """
    findings = []
    for line in read(LOGS / "trufflehog.json").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        git = item.get("SourceMetadata", {}).get("Data", {}).get("Git", {})
        if "DetectorName" not in item:
            continue
        findings.append((
            item["DetectorName"],
            item.get("Verified"),
            git.get("file", "?"),
            git.get("line", 0),
            git.get("commit", "?")[:10],
        ))
    if not findings:
        log = read(LOGS / "trufflehog.err")[-MAX_LOG_TAIL:]
        return f"trufflehog exited non-zero but reported no findings. Its log:\n{block(log)}"
    rows = ["| Detector | Verified | File | Line | Commit |", "|---|---|---|---|---|"]
    for detector, verified, file, line, commit in findings:
        rows.append(f"| {detector} | {'yes (live!)' if verified else 'unverified'} | `{file}` | {line} | `{commit}` |")
        annotate(file, line or 1, f"trufflehog: possible {detector} secret")
    fix = (
        "**Fix:**\n"
        "1. Treat every verified hit as leaked: **rotate the credential now**."
        " Removing it from git does not un-leak it.\n"
        "2. Remove the secret from the code and load it from the environment or a secret store.\n"
        "3. The secret lives in git history, so a new commit is not enough. Rewrite the branch "
        "(`git rebase -i` / `git filter-repo`) before it is merged.\n"
        "4. False positive? Add `trufflehog:ignore` on the line."
    )
    return "\n".join(rows) + "\n\n" + fix


def semgrep() -> str:
    """Report the findings of semgrep.

    Returns
    -------
    str
        The markdown with the failure and how to fix it.

    """
    try:
        data = json.loads(read(LOGS / "semgrep.json"))
    except json.JSONDecodeError:
        return f"semgrep produced no report. Its log:\n{block(read(LOGS / 'semgrep.log')[-MAX_LOG_TAIL:])}"
    rows = ["| Rule | Location | Message |", "|---|---|---|"]
    for result in data.get("results", []):
        path, line = result["path"], result["start"]["line"]
        message = result["extra"]["message"].strip().splitlines()[0]
        rule = result["check_id"].rsplit(".", 1)[-1]
        rows.append(f"| `{rule}` | `{path}:{line}` | {message} |")
        annotate(path, line, f"semgrep {result['check_id']}: {message}")
    rows.extend(f"| error | | {err.get('message', err)} |" for err in data.get("errors", []))
    fix = (
        "**Fix:** change the flagged code as the message says."
        " Full rule text: `uvx semgrep scan --config p/default`.\n"
        "False positive? Add `# nosemgrep: <rule id>` on the line with a short reason."
    )
    return "\n".join(rows) + "\n\n" + fix


def trivy() -> str:
    """Report the vulnerabilities, secrets and misconfigurations that trivy found.

    Returns
    -------
    str
        The markdown with the failure and how to fix it.

    """
    try:
        data = json.loads(read(LOGS / "trivy.json"))
    except json.JSONDecodeError:
        return f"trivy produced no report. Its log:\n{block(read(LOGS / 'trivy.log')[-MAX_LOG_TAIL:])}"
    rows = ["| Kind | Target | Finding | Fix |", "|---|---|---|---|"]
    bumps: set[str] = set()
    for result in data.get("Results") or []:
        target = result["Target"]
        for vuln in result.get("Vulnerabilities") or []:
            fixed = vuln.get("FixedVersion", "")
            rows.append(
                f"| {vuln['Severity']} vuln | `{target}` | {vuln['VulnerabilityID']} in "
                f"`{vuln['PkgName']} {vuln['InstalledVersion']}` | upgrade to {fixed or 'n/a'} |",
            )
            if fixed:
                bumps.add(vuln["PkgName"])
        for secret in result.get("Secrets") or []:
            rows.append(
                f"| secret | `{target}:{secret.get('StartLine', '?')}` | {secret['Title']} | remove and rotate |",
            )
            annotate(target, secret.get("StartLine", 1), f"trivy: {secret['Title']}")
        rows.extend(
            f"| {misconf['Severity']} misconfig | `{target}` | {misconf['ID']}: {misconf['Title']} |"
            f" {misconf.get('Resolution', '')} |"
            for misconf in result.get("Misconfigurations") or []
        )
    fix = ["**Fix:**"]
    if bumps:
        upgrades = " ".join(f"--upgrade-package {name}" for name in sorted(bumps))
        fix.append(
            f"- Vulnerable dependencies: `uv lock {upgrades}`, then `uv sync` and rerun the tests. Commit `uv.lock`.",
        )
    fix.extend((
        "- Secrets: remove, rotate the credential, load it from the environment.",
        "- Misconfigurations: apply the resolution in the table.",
        "- Not exploitable here? Add the ID to `.trivyignore` with a comment saying why.",
    ))
    return clip("\n".join(rows), MAX_CHARS) + "\n\n" + "\n".join(fix)


def pytest() -> str:
    """Report the failing tests and the files that lack coverage.

    Returns
    -------
    str
        The markdown with the failure and how to fix it.

    """
    log = read(LOGS / "pytest.log")
    parts = []
    failures: list[str] = re.findall(r"^(?:FAILED|ERROR) .+$", log, re.MULTILINE)
    if failures:
        parts.append(
            "**Failing tests**\n"
            + block("\n".join(failures))
            + "\n**Fix:** reproduce with `uv run pytest -x <test id>`. "
            "The traceback is in the job log under the `FAILURES` heading.",
        )
        for failure in failures:
            if m := re.match(r"^(?:FAILED|ERROR) (\S+?\.py)::", failure):
                annotate(m.group(1), 1, failure)
    short = []
    for m in re.finditer(r"^(\S+\.py)\s+\d+\s+(\d+)\s+\d+\s+(\d+)\s+(\d+)%\s*(.*)$", log, re.MULTILINE):
        path, missed, partial, cover, missing = m.groups()
        if int(cover) < PERCENT:
            short.append(
                f"{path}: {cover}% | missed statements: {missed}, partial branches: {partial}"
                f" | lines: {missing or '-'}",
            )
    if short or "Required test coverage" in log:
        total = re.search(r"^TOTAL\s.*?(\d+)%", log, re.MULTILINE)
        head = f"**Coverage {total.group(1)}%, 100% required**\n" if total else "**Coverage below 100%**\n"
        parts.append(
            head
            + block("\n".join(short) or "see the coverage table in the job log")
            + "\n**Fix:** write tests that execute "
            "the listed lines and branches (`a->b` means the branch from line a to b is never taken). Check locally: "
            "`uv run pytest` and read the `Missing` column. Do not add `# pragma: no cover` to dodge this.",
        )
    if not parts:
        parts.append(f"pytest failed without a recognized summary. Last output:\n{block(log[-MAX_LOG_TAIL:])}")
    return "\n\n".join(parts)


def mutation() -> str:
    """Report the mutants that survived.

    Returns
    -------
    str
        The markdown with the failure and how to fix it.

    """
    log = read(LOGS / "mutation.log")
    survivors = read(LOGS / "mutation-survivors.txt")
    if "Baseline failed" in log:
        return (
            f"**Baseline failed: the test suite fails or times out with no mutation applied**\n{block(log[-2500:])}\n"
            "**Fix:** make `uv run pytest -x -o addopts='' tests/unit` pass on its own first. If it only times out, "
            "raise `timeout` in `cosmic-ray.toml`; CI runners are slower than laptops."
        )
    rate = re.search(r"survival rate: ([\d.]+)%", log)
    head = f"**{rate.group(1)}% of mutants survived, 0% allowed**\n" if rate else "**Surviving mutants**\n"
    return (
        head
        + block(survivors or log[-MAX_LOG_TAIL:])
        + "\n**Fix:** each diff above is a bug the tests did not notice: the `-` line is the real code, "
        "the `+` line the mutant. Add a test that fails when the code is changed that way "
        "(assert on the exact value or boundary). "
        "Equivalent mutant (no test can tell the difference)? Simplify the code so it does not exist. "
        "Reproduce locally: `uv run python scripts/mutation.py`."
    )


BUILDERS = {fn.__name__: fn for fn in (prek, trufflehog, semgrep, trivy, pytest, mutation)}


def snippet(gate: str) -> None:
    """Write the report of a failed gate to ``$CI_REPORT/<gate>.md``.

    Parameters
    ----------
    gate: str
        The job id of the gate.

    """
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / f"{gate}.md").write_text(BUILDERS[gate]() + "\n")


def run_url() -> str:
    """Build the URL of the workflow run.

    Returns
    -------
    str
        The URL of the run, from the variables of the runner.

    """
    server, repository, run_id = (os.environ[k] for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repository}/actions/runs/{run_id}"


def api(method: str, path: str, payload: Mapping[str, object] | None = None) -> Any:  # ruff: ignore[any-type] -- the GitHub API returns JSON of many shapes
    """Call the GitHub REST API with the token of the job.

    Parameters
    ----------
    method: str
        The HTTP method.
    path: str
        The path of the endpoint, with its query.
    payload: Mapping[str, object], optional
        The JSON body.

    Returns
    -------
    Any
        The decoded JSON of the response.

    Raises
    ------
    ValueError
        If ``GITHUB_API_URL`` is not an http or https URL.

    """
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    if not base.startswith(("https://", "http://")):  # urllib also opens file: URLs, so allow only web schemes
        msg = f"GITHUB_API_URL must be an http(s) URL: {base}"
        raise ValueError(msg)
    request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage] -- the scheme of the URL is checked above
        f"{base}{path}",
        data=None if payload is None else json.dumps(payload).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    # The scheme of the URL is checked above, and the host comes from the runner.
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected  # ruff: ignore[commented-out-code] -- semgrep marker, not code
    with urllib.request.urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage] -- the scheme of the URL is checked above
        return json.load(response)


def pull_request_number() -> int:
    """Read the number of the pull request from the event of the run.

    Returns
    -------
    int
        The number of the pull request.

    """
    return int(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))["pull_request"]["number"])


def upsert_comment(text: str) -> None:
    """Create the PR comment, or replace the text of the comment that has ``MARKER``.

    Parameters
    ----------
    text: str
        The markdown of the comment, without the marker.

    """
    repository = os.environ["GITHUB_REPOSITORY"]
    number = pull_request_number()
    body = f"{MARKER}\n{text}"
    page = 1
    while True:
        comments = api("GET", f"/repos/{repository}/issues/{number}/comments?per_page={PAGE_SIZE}&page={page}")
        for comment in comments:
            if MARKER in comment["body"]:
                api("PATCH", f"/repos/{repository}/issues/comments/{comment['id']}", {"body": body})
                return
        if len(comments) < PAGE_SIZE:
            break
        page += 1
    api("POST", f"/repos/{repository}/issues/{number}/comments", {"body": body})


def gate_states(jobs: Sequence[Mapping[str, str | None]]) -> dict[str, str]:
    """Find the state of each gate in the jobs of the run.

    Parameters
    ----------
    jobs: Sequence[Mapping[str, str | None]]
        The jobs of the run, as the GitHub API returns them.

    Returns
    -------
    dict[str, str]
        The state of each gate: ``waiting``, ``running``, or the conclusion of the job.

    """
    states = {gate: "waiting" for gate, _ in GATES}
    for job in jobs:
        name = job["name"] or ""
        for gate, _ in GATES:
            if name == gate or name.startswith(f"{gate} "):
                if job["status"] == "completed":
                    states[gate] = job["conclusion"] or "cancelled"
                elif job["status"] == "in_progress":
                    states[gate] = "running"
    return states


def render_progress(states: Mapping[str, str]) -> str:
    """Write the comment for a run that has not finished.

    Parameters
    ----------
    states: Mapping[str, str]
        The state of each gate, from ``gate_states``.

    Returns
    -------
    str
        The markdown of the comment.

    """
    icons = {
        "waiting": "⏳ waiting",
        "running": "🔄 running",
        "success": "✅ passed",
        "failure": "❌ **failed**, details follow when the run ends",
        "cancelled": "🚫 cancelled",
        "skipped": "⏭️ skipped (no relevant change, or blocked by an earlier gate)",
    }
    finished = sum(state in FINISHED for state in states.values())
    failed = sum(state == "failure" for state in states.values())
    heading = f"## 🔄 CI in progress: {finished} of {len(GATES)} gates finished"
    if failed:
        heading += f", {failed} failed"
    lines = [heading, "", "This comment updates by itself when a gate changes. The final report replaces it.", ""]
    lines += ["| Gate | State |", "|---|---|"]
    lines += [f"| {title} | {icons.get(states[gate], states[gate])} |" for gate, title in GATES]
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    lines += ["", f"<sub>Commit `{sha}` · [live run logs]({run_url()})</sub>", ""]
    return "\n".join(lines)


def update_progress(posted: str) -> tuple[bool, str]:
    """Read the state of the gates and update the PR comment if the state changed.

    Parameters
    ----------
    posted: str
        The text that the last update wrote.

    Returns
    -------
    tuple[bool, str]
        Whether all gates have finished, and the text that the PR comment now holds.

    """
    repository, run_id = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"]
    states = gate_states(api("GET", f"/repos/{repository}/actions/runs/{run_id}/jobs?per_page={PAGE_SIZE}")["jobs"])
    if all(state in FINISHED for state in states.values()):
        return True, posted
    text = render_progress(states)
    if text != posted:
        upsert_comment(text)
    return False, text


def watch() -> None:
    """Update the PR comment with the state of the gates until all gates have finished."""
    deadline = time.monotonic() + WATCH_LIMIT_SECONDS
    posted = ""
    while time.monotonic() < deadline:
        try:
            done, posted = update_progress(posted)
        except urllib.error.HTTPError as error:
            if error.code in FORBIDDEN:  # a fork PR has a read-only token, so there is nothing to update
                return
            sys.stderr.write(f"progress update failed: {error}\n")
        except urllib.error.URLError as error:
            sys.stderr.write(f"progress update failed: {error}\n")
        else:
            if done:
                return
        time.sleep(POLL_SECONDS)


def post(path: str) -> None:
    """Create the PR comment from a file, or replace the existing comment.

    Parameters
    ----------
    path: str
        The markdown file.

    Raises
    ------
    urllib.error.HTTPError
        If the API refuses the request for a reason other than missing write access.

    """
    try:
        upsert_comment(Path(path).read_text(encoding="utf-8"))
    except urllib.error.HTTPError as error:
        if error.code not in FORBIDDEN:
            raise
        sys.stderr.write("no write access to the PR (a fork PR?); the report stays in the run summary\n")


def assemble() -> None:
    """Combine the snippets and the job results into the PR comment and the step summary."""
    needs = json.loads(os.environ["NEEDS"])
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    icons = {
        "success": "✅ passed",
        "failure": "❌ **failed**",
        "cancelled": "🚫 cancelled",
        "skipped": "⏭️ skipped (no relevant change, or blocked by an earlier gate)",
    }
    results = {gate: needs.get(gate, {}).get("result", "skipped") for gate, _ in GATES}
    failed = [(gate, title) for gate, title in GATES if results[gate] == "failure"]

    if failed:
        lines = [f"## ❌ CI failed: {len(failed)} of {len(GATES)} gates", ""]
    elif all(r in {"success", "skipped"} for r in results.values()):
        # With no failure, a skipped gate is one that the changed files cannot affect (see `changes` in ci.yml).
        passed = sum(r == "success" for r in results.values())
        lines = ["## ✅ CI passed", "", f"{passed} of {len(GATES)} gates green on `{sha}`; the others need no run."]
    else:
        lines = ["## ⚠️ CI did not finish", ""]
    lines += ["| Gate | Result |", "|---|---|"]
    lines += [f"| {title} | {icons.get(results[gate], results[gate])} |" for gate, title in GATES]
    lines.append("")
    for gate, title in failed:
        path = REPORT / f"{gate}.md"
        body = (
            read(path) or "The job failed before the tool produced a report (setup or runner error). Open the job log."
        )
        lines += [f"### ❌ {title}", "", body.strip(), ""]
    lines.append(f"<sub>Commit `{sha}` · [full run logs]({run_url()})</sub>")
    text = "\n".join(lines) + "\n"
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "comment.md").write_text(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    """Run the subcommand given on the command line.

    Returns
    -------
    int
        The exit code: 0 on success, 2 on a usage error.

    """
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "snippet" and len(sys.argv) == SNIPPET_ARGC and sys.argv[2] in BUILDERS:
        snippet(sys.argv[2])
    elif command == "assemble":
        assemble()
    elif command == "watch":
        watch()
    elif command == "post" and len(sys.argv) == POST_ARGC:
        post(sys.argv[2])
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
