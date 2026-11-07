"""The `review-receipt` required check: no PR merges without an independent review (JEG-1551).

Jeremy, 2026-11-06, picked A: green, Codex-reviewed PRs merge themselves
through the merge queue; his approval stays only for deploys and value math.
This check is the review half of that. It passes when:

1. the PR is not a draft;
2. a review on the PR says `ddf-review: PASS` and was left on the current head,
   or on an older head whose net change is identical (a clean catch-up merge of
   main: same files, same contents), and no later `ddf-review: FAIL` exists;
3. a PR that changes value math or a database migration carries the
   `jeremy-approved` label, which only Jeremy asks for;
4. the PR does not edit HANDOFF.md (the shared notes file that made PRs
   conflict) unless it carries the `handoff-edit` label.

On a merge_group event the PR was already checked before it entered the
queue, so the check passes. Any API doubt fails closed.

    python3 -m pipelines.review_receipt check
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from urllib.request import Request, urlopen

PASS_RE = re.compile(r"ddf-review:\s*PASS\b", re.I)
FAIL_RE = re.compile(r"ddf-review:\s*FAIL\b", re.I)
APPROVAL_LABEL = "jeremy-approved"
HANDOFF_LABEL = "handoff-edit"
# pipelines/build_values_explainer.py LOGIC_FILES (kept equal by a test), plus
# the value config and the bake, plus database migrations.
VALUE_MATH = (
    "app/trade-value-chart/assets/value-model.js",
    "app/trade-value-chart/assets/curve-widget.js",
    "pipelines/value_reference.py",
    "pipelines/spec_reference/value_pipeline.py",
    "docs/methodology.md",
    "config/lineup_parameters.json",
    "config/roster.json",
    "pipelines/bake_players.py",
)
MIGRATIONS = ("sql/migrations/*", "supabase/migrations/*")
HANDOFF = "HANDOFF.md"
FILE_LIMIT = 3000  # the PR files API stops at 3000


def _api(path, token):
    request = Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def needs_jeremy(files):
    """Changed files that need Jeremy's own yes before merging."""
    out = []
    for name in files:
        if name in VALUE_MATH or any(fnmatch.fnmatch(name, p) for p in MIGRATIONS):
            out.append(name)
    return out


def net_change(compare_payload):
    """{filename: blob sha} for a base...head comparison; removed files map to None."""
    out = {}
    for f in compare_payload.get("files") or []:
        out[f["filename"]] = None if f.get("status") == "removed" else f.get("sha")
    return out


def latest_verdicts(reviews):
    """[(commit_id, 'PASS'|'FAIL')] in submission order."""
    out = []
    for review in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        body = review.get("body") or ""
        if review.get("state") == "DISMISSED":
            continue
        if FAIL_RE.search(body):
            out.append((review.get("commit_id"), "FAIL"))
        elif PASS_RE.search(body):
            out.append((review.get("commit_id"), "PASS"))
    return out


def evaluate(pr, files, reviews, same_change):
    """Return (ok, reasons). same_change(sha) -> True when sha's net change equals head's."""
    reasons = []
    head = (pr.get("head") or {}).get("sha")
    labels = {label.get("name") for label in pr.get("labels") or []}
    if pr.get("draft"):
        reasons.append("PR is a draft")
    if files is None:
        reasons.append("changed-file list unavailable or too long")
        files = []
    verdicts = latest_verdicts(reviews)
    if not verdicts:
        reasons.append("no `ddf-review: PASS` review yet")
    else:
        commit, verdict = verdicts[-1]
        if verdict == "FAIL":
            reasons.append(f"latest review verdict is FAIL (on {str(commit)[:12]})")
        elif commit != head and not same_change(commit):
            reasons.append(f"review is on {str(commit)[:12]}, not the current head "
                           f"{str(head)[:12]}, and the change differs: review the delta")
    held = needs_jeremy(files)
    if held and APPROVAL_LABEL not in labels:
        reasons.append(f"value math or a migration changes ({', '.join(held[:5])}): "
                       f"needs Jeremy's yes (`{APPROVAL_LABEL}` label)")
    if HANDOFF in files and HANDOFF_LABEL not in labels:
        reasons.append(f"edits {HANDOFF}; put notes in docs/claude-log or Linear "
                       f"(or `{HANDOFF_LABEL}` label for a deliberate edit)")
    return not reasons, reasons


def check(environ=None, fetch_api=None):
    environ = os.environ if environ is None else environ
    event_name = environ.get("GITHUB_EVENT_NAME", "")
    if event_name == "merge_group":
        return True, ["merge queue: the PR passed this check before it was queued"]
    payload = {}
    path = environ.get("GITHUB_EVENT_PATH")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    number = (payload.get("pull_request") or {}).get("number") \
        or (payload.get("issue") or {}).get("number")
    if not number:
        return False, [f"{event_name or 'unknown'} event names no pull request"]
    if fetch_api is None:
        repo, token = environ.get("GITHUB_REPOSITORY"), environ.get("GH_TOKEN")

        def fetch_api(api_path):
            if not repo or not token:
                raise ValueError("repository or token unavailable")
            return _api(f"repos/{repo}/{api_path}", token)

    try:
        pr = fetch_api(f"pulls/{number}")
        files, page = [], 1
        while True:
            batch = fetch_api(f"pulls/{number}/files?per_page=100&page={page}")
            files.extend(f["filename"] for f in batch)
            if len(batch) < 100:
                break
            page += 1
        if len(files) >= FILE_LIMIT:
            files = None
        reviews, page = [], 1
        while True:
            batch = fetch_api(f"pulls/{number}/reviews?per_page=100&page={page}")
            reviews.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    except Exception as error:  # noqa: BLE001 - fail closed
        return False, [f"GitHub API unavailable ({type(error).__name__})"]

    base = (pr.get("base") or {}).get("ref") or "main"
    head = (pr.get("head") or {}).get("sha")

    def same_change(sha):
        if not sha or not head:
            return False
        try:
            then = net_change(fetch_api(f"compare/{base}...{sha}"))
            now = net_change(fetch_api(f"compare/{base}...{head}"))
        except Exception:  # noqa: BLE001 - doubt means re-review
            return False
        return bool(now) and then == now

    return evaluate(pr, files, reviews, same_change)


def main(argv):
    if argv[1:] != ["check"]:
        print("usage: python3 -m pipelines.review_receipt check", file=sys.stderr)
        return 2
    ok, reasons = check()
    lines = [("review-receipt: PASS" if ok else "review-receipt: not yet")] + \
        [f"- {r}" for r in reasons]
    print("\n".join(lines))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
