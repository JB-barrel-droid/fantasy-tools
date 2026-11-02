"""Fail closed before PR promotion/merge. REST evidence plus optional local Git.

Exit 0: fresh and green; 1: refused; 2: API/input evidence unavailable.
--informational reports the verdict without failing the workflow, excluding
only that workflow's own running check. Never use that mode for promotion.
The #1255 registry attributes failures; it does not waive red check statuses.
Bot catch-up policy is in pr_freshness_config.json; both flags default off.
There is no environment override. Enabling either needs Jeremy's standing yes.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = "JB-barrel-droid/fantasy-tools"
REGISTRY = "docs/baseline-reds/registry.json"
SHA = re.compile(r"[0-9a-f]{40}")
CONFIG = Path(__file__).with_name("pr_freshness_config.json")
# Reviewed repository policy (runbooks/merging-prs.md), independent of which
# workflows have registered so far. No caller/config override or absent-by-path
# exemption: the full-CI finalizers must actually succeed before promotion.
REQUIRED_CHECKS = frozenset({"preview", "v2-render"})


class EvidenceError(ValueError):
    pass


class NotFound(EvidenceError):
    pass


def load_config(path=CONFIG):
    config = json.loads(path.read_text(encoding="utf-8"))
    for flag in ("allow_bot_only_behind", "allow_bot_data_inputs"):
        if type(config[flag]) is not bool:
            raise EvidenceError("invalid bot catch-up flag")
    for group in ("status_only", "data_inputs"):
        paths = config[group]
        if not isinstance(paths, list) or any(
            not isinstance(p, str) or not p or p.startswith("/")
            or any(part in ("", ".", "..") for part in p.split("/"))
            or re.search(r"[\x00-\x1f\\]", p)
            or ("*" in p and (not p.endswith("/**") or "*" in p[:-3]))
            or "?" in p or "[" in p for p in paths
        ):
            raise EvidenceError("invalid bot catch-up paths")
    authors = config["bot_authors"]
    if not isinstance(authors, list) or not authors or any(
        not isinstance(a, dict) or not isinstance(a.get("name"), str)
        or not a["name"] or not isinstance(a.get("email"), str) or not a["email"]
        for a in authors
    ):
        raise EvidenceError("invalid bot author identities")
    return config


class LocalGit:
    """Use only existing local objects/refs; do not fetch or touch the worktree."""

    def __init__(self, root=None):
        self.root = root or Path(__file__).resolve().parents[1]

    def run(self, *args):
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(self.root), *args],
            env=dict(os.environ, GIT_NO_LAZY_FETCH="1"), text=True,
            capture_output=True, timeout=30, check=False,
        )
        if result.returncode:
            raise EvidenceError("local Git evidence unavailable or merge-tree conflicted")
        return result.stdout

    def main_sha(self):
        return sha(self.run("rev-parse", "--verify", "refs/remotes/origin/main^{commit}").strip())


def allowed_path(path, patterns):
    return any(path == p or (p.endswith("/**") and path.startswith(p[:-2]))
               for p in patterns)


def bot_only_behind(git, head, main, behind, config):
    """Return a refusal or the exact skipped commits; inspect every intermediate write."""
    if git.main_sha() != main:
        return [], "local origin/main differs from observed main; fetch before gating"
    bases = git.run("merge-base", "--all", head, main).splitlines()
    if len(bases) != 1:
        return [], "bot-only-behind requires one unambiguous merge base"
    base = sha(bases[0])
    commits = [sha(c) for c in git.run("rev-list", "--reverse", f"{base}..{main}").splitlines()]
    if not commits or len(commits) != behind:
        return [], "local behind history disagrees with REST compare"
    changed = set(git.run("diff", "--name-only", "--no-renames", "-z", base, head).split("\0")) - {""}
    patterns = list(config["status_only"])
    if config["allow_bot_data_inputs"]:
        patterns.extend(config["data_inputs"])
    identities = {(a["name"], a["email"]) for a in config["bot_authors"]}
    for commit in commits:
        identity = git.run("show", "-s", "--format=%an%x00%ae", commit).rstrip("\n").split("\0")
        if tuple(identity) not in identities:
            return [], f"bot-only-behind refused: non-bot author at {commit}"
        # -m checks merge commits against every parent; --no-renames exposes
        # both sides of a rename. Never hide a transient write or a deletion.
        paths = set(git.run("diff-tree", "--no-commit-id", "--root", "-r", "-m",
                            "--name-only", "--no-renames", "-z", commit).split("\0")) - {""}
        if paths & changed:
            return [], f"bot-only-behind refused: PR file overlap at {commit}"
        if any(not allowed_path(p, patterns) for p in paths):
            return [], f"bot-only-behind refused: path outside enabled allowlists at {commit}"
    try:
        # This writes Git tree objects only, not an index/worktree or a merge commit.
        git.run("merge-tree", "--write-tree", head, main)
    except EvidenceError:
        return [], "bot-only-behind refused: merge-tree not clean or evidence unavailable"
    if git.main_sha() != main:
        return [], "local origin/main moved during bot-only verification"
    return commits, None


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


def evaluate(api, number=None, group_head=None, informational_run=None, config=None, local_git=None):
    config = load_config() if config is None else config
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
    skipped = []
    if behind:
        if not config["allow_bot_only_behind"]:
            return 1, f"head is behind main by {behind} commit(s); merge origin/main first"
        skipped, refusal = bot_only_behind(local_git or LocalGit(), head, main, behind, config)
        if refusal:
            return 1, refusal
    entries = registry(api, main)
    checks, states = check_runs(api, head), statuses(api, head)
    considered = 0
    passed_required = set()
    for check in checks:
        if sha(check["head_sha"]) != head:
            raise EvidenceError("check run is for another head")
        if own_information_check(check, api.repo, informational_run):
            continue
        considered += 1
        if check["status"] != "completed":
            return 1, "head has a pending check run"
        conclusion = check.get("conclusion")
        if check.get("name") in REQUIRED_CHECKS:
            if (conclusion != "success"
                    or check.get("app", {}).get("slug") != "github-actions"):
                return 1, "required check must succeed in GitHub Actions: " + check["name"]
            passed_required.add(check["name"])
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
    missing = REQUIRED_CHECKS - passed_required
    if missing:
        return 1, "head is missing required checks: " + ", ".join(sorted(missing))
    # Detect concurrent head/base movement. This is a new observation, not a retry.
    if sha(api.get("commits/main")["sha"]) != main:
        return 1, "main moved during verification"
    if pull is not None:
        current = api.get(f"pulls/{number}")
        if current["state"] != "open" or sha(current["head"]["sha"]) != head:
            return 1, "PR closed or head moved during verification"
    if skipped:
        return 0, (f"bot-only-behind: {head[:12]}; all {considered} checks/statuses accepted; "
                   f"skipped bot commits: {','.join(skipped)}")
    return 0, f"fresh: {head[:12]} contains current main; all {considered} checks/statuses accepted"


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
