"""Fail closed before PR promotion/merge. REST only; no retries.

Exit 0: fresh and green; 1: refused; 2: API/input evidence unavailable.
--informational reports the verdict without failing the workflow, excluding
only that workflow's own running check. Never use that mode for promotion.
The #1255 registry attributes failures; it does not waive red check statuses.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys

REPO = "JB-barrel-droid/fantasy-tools"
REGISTRY = "docs/baseline-reds/registry.json"
SHA = re.compile(r"[0-9a-f]{40}")


class EvidenceError(ValueError):
    pass


class NotFound(EvidenceError):
    pass


class Rest:
    """Let gh handle authentication without reading or printing credentials."""

    def __init__(self, repo):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise EvidenceError("invalid repository")
        self.repo = repo

    def get(self, path):
        result = subprocess.run(
            ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json",
             "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{self.repo}/{path}"],
            text=True, capture_output=True, timeout=30, check=False,
        )
        if result.returncode:
            # Do not echo API bodies/stderr (which can contain private input).
            if "(HTTP 404)" in result.stderr:
                raise NotFound("REST resource not found")
            raise EvidenceError("REST request failed")
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise EvidenceError("REST returned invalid JSON") from exc


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise EvidenceError("commit SHA unavailable")
    return value


def check_runs(api, head):
    rows = []
    page = 1
    while True:
        data = api.get(f"commits/{head}/check-runs?filter=latest&per_page=100&page={page}")
        batch, total = data["check_runs"], data["total_count"]
        if (not isinstance(batch, list) or type(total) is not int or total < 0
                or len(batch) > 100):
            raise EvidenceError("invalid check-run response")
        rows.extend(batch)
        if len(rows) == total:
            return rows
        if not batch or len(rows) > total:
            raise EvidenceError("incomplete check-run evidence")
        page += 1


def statuses(api, head):
    rows = []
    page = 1
    while True:
        data = api.get(f"commits/{head}/status?per_page=100&page={page}")
        if sha(data["sha"]) != head:
            raise EvidenceError("status response is for another head")
        batch, total = data["statuses"], data["total_count"]
        if (not isinstance(batch, list) or type(total) is not int or total < 0
                or len(batch) > 100):
            raise EvidenceError("invalid status response")
        rows.extend(batch)
        if len(rows) == total:
            return rows
        if not batch or len(rows) > total:
            raise EvidenceError("incomplete status evidence")
        page += 1


def registry(api, main):
    """Read only the registry committed on main, never a PR's proposed waiver."""
    try:
        data = api.get(f"contents/{REGISTRY}?ref={main}")
    except NotFound:
        return []
    if data.get("encoding") != "base64":
        raise EvidenceError("invalid baseline registry encoding")
    entries = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
    if not isinstance(entries, list) or any(
        not isinstance(e, dict) or not isinstance(e.get("test_id"), str)
        or not isinstance(e.get("where"), list) for e in entries
    ):
        raise EvidenceError("invalid baseline registry")
    return entries


def path_skip(check):
    # GitHub's generic 'skipped' also includes draft/condition skips. Require
    # an explicit path-skip receipt from the producing check, not its name.
    output = check.get("output") or {}
    return any("skipped-by-path" in (output.get(key) or "").lower()
               for key in ("title", "summary", "text"))


def own_information_check(check, repo, run_id):
    # A workflow cannot wait for its own check to complete. Only the exact
    # Actions run/job URL and job name may be excluded, in informational mode.
    return (run_id is not None and check.get("name") == "PR freshness (informational)"
            and check.get("app", {}).get("slug") == "github-actions"
            and re.fullmatch(
                rf"https://github\.com/{re.escape(repo)}/actions/runs/{re.escape(run_id)}/job/\d+",
                check.get("details_url") or "") is not None)


def evaluate(api, number=None, group_head=None, informational_run=None):
    main = sha(api.get("commits/main")["sha"])
    pull = api.get(f"pulls/{number}") if number is not None else None
    if pull is not None and (pull["state"] != "open" or pull["base"]["ref"] != "main"
                             or pull["base"]["repo"]["full_name"] != api.repo):
        return 1, "PR must be open against this repository's main"
    head = sha(pull["head"]["sha"] if pull is not None else group_head)
    comparison = api.get(f"compare/main...{head}")
    behind = comparison["behind_by"]
    if type(behind) is not int or behind < 0:
        raise EvidenceError("compare behind_by unavailable")
    if behind:
        return 1, f"head is behind main by {behind} commit(s); merge origin/main first"
    entries = registry(api, main)
    checks, states = check_runs(api, head), statuses(api, head)
    considered = 0
    for check in checks:
        if sha(check["head_sha"]) != head:
            raise EvidenceError("check run is for another head")
        if own_information_check(check, api.repo, informational_run):
            continue
        considered += 1
        if check["status"] != "completed":
            return 1, "head has a pending check run"
        conclusion = check.get("conclusion")
        if conclusion in ("success", "neutral"):
            continue
        if conclusion == "skipped" and path_skip(check):
            continue
        suffix = "; baseline registry is attribution only" if entries else ""
        return 1, "head has a failing or unproven-skipped check run" + suffix
    for status in states:
        considered += 1
        if status["state"] != "success":
            return 1, "head has a pending or failing commit status"
    if not considered:
        return 1, "head has no completed check/status evidence"
    # Detect concurrent head/base movement. This is a new observation, not a retry.
    if sha(api.get("commits/main")["sha"]) != main:
        return 1, "main moved during verification"
    if pull is not None:
        current = api.get(f"pulls/{number}")
        if current["state"] != "open" or sha(current["head"]["sha"]) != head:
            return 1, "PR closed or head moved during verification"
    return 0, f"{head[:12]} contains current main; all {considered} checks/statuses accepted"


def main(argv=None, api=None, environ=None):
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("number", nargs="?", type=int)
    target.add_argument("--merge-group", metavar="HEAD_SHA")
    parser.add_argument("--repo", default=REPO)
    parser.add_argument("--informational", action="store_true")
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        run_id = None
        if args.number is not None and args.number <= 0:
            raise EvidenceError("invalid PR number")
        if args.informational:
            run_id = env.get("GITHUB_RUN_ID", "")
            if (env.get("GITHUB_ACTIONS") != "true" or not run_id.isdigit()
                    or env.get("GITHUB_WORKFLOW") != "PR freshness"
                    or env.get("GITHUB_REPOSITORY") != args.repo):
                raise EvidenceError("informational mode requires the PR freshness Actions workflow")
        code, reason = evaluate(api or Rest(args.repo), args.number, args.merge_group, run_id)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        code, reason = 2, "API/input evidence unavailable; refusing closed (no retry)"
    print(f"{'PASS' if code == 0 else 'REFUSED'}: {reason}")
    return 0 if args.informational else code


if __name__ == "__main__":
    sys.exit(main())
