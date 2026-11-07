"""The `review-receipt` required check: no PR merges without an independent review (JEG-1551).

Jeremy, 2026-11-06, picked A: green, Codex-reviewed PRs merge themselves
through the merge queue; his approval stays only for deploys and value math.
This check is the review half of that. It passes when:

1. the PR is not a draft;
2. the latest verdict from an independent reviewer is a pass, given on the
   current head, or on an older head whose net change is identical (a clean
   catch-up merge of main: same files, same contents, complete comparison);
3. a PR that changes value math or a database migration carries the
   `jeremy-approved` label, which only Jeremy asks for;
4. the PR does not edit HANDOFF.md (the shared notes file that made PRs
   conflict) unless it carries the `handoff-edit` label.

Independent reviewer. Every agent posts to GitHub from the same account as the
PR author, so a `ddf-review:` comment from that account proves nothing. A
verdict counts only from:

- the Codex GitHub app (`chatgpt-codex-connector[bot]`), which reviews a PR
  when it is opened or marked ready and on an `@codex review` comment: a
  review on a head with no P0 or P1 finding is a pass, one with a P0 or P1
  finding is a fail, and its thumbs-up on the PR after the head was pushed is
  a pass for that head;
- a login listed in the repository variable DDF_REVIEW_LOGINS (never the PR
  author), whose COMMENT review's first line is exactly `ddf-review: PASS` or
  `ddf-review: FAIL`.

The workflow runs on pull_request_target, so both it and this script come
from main, never from the PR. On a merge_group event the PR was already
checked before it entered the queue, so the check passes. Any API doubt fails
closed.

    python3 -m pipelines.review_receipt check
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from urllib.request import Request, urlopen

CODEX_APP = "chatgpt-codex-connector[bot]"
BLOCKING_FINDING_RE = re.compile(r"!\[P[01] Badge\]")
VERDICT_RE = re.compile(r"\Addf-review:[ \t]*(PASS|FAIL)[ \t]*\r?$", re.M)
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
COMPARE_FILE_LIMIT = 300  # the compare API returns at most 300 files


def _api(path, token):
    request = Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def file_names(batch):
    """Both names of a renamed file: a rename away from value math still changes it."""
    out = []
    for f in batch:
        for key in ("filename", "previous_filename"):
            if f.get(key):
                out.append(f[key])
    return out


def needs_jeremy(files):
    """Changed files that need Jeremy's own yes before merging."""
    out = []
    for name in files:
        if name in VALUE_MATH or any(fnmatch.fnmatch(name, p) for p in MIGRATIONS):
            out.append(name)
    return out


def net_change(compare_payload):
    """{filename: blob sha} for a complete base...head comparison, or None when it may be cut off."""
    files = compare_payload.get("files")
    if files is None or len(files) >= COMPARE_FILE_LIMIT:
        return None
    out = {}
    for f in files:
        out[f["filename"]] = None if f.get("status") == "removed" else f.get("sha")
        if f.get("previous_filename"):
            out.setdefault(f["previous_filename"], None)
    return out


def first_line_verdict(body):
    match = VERDICT_RE.match(body or "")
    return match.group(1) if match else None


def verdicts(reviews, review_comments, reactions, head, head_pushed_at, author,
             reviewers=()):
    """[(time, commit, 'PASS'|'FAIL')] from independent reviewers, oldest first.

    review_comments maps a review id to its inline comment bodies.
    """
    out = []
    allowed = {r.lower() for r in reviewers if r} - {(author or "").lower()}
    for review in reviews:
        if review.get("state") == "DISMISSED":
            continue
        login = (review.get("user") or {}).get("login") or ""
        at, commit = review.get("submitted_at") or "", review.get("commit_id")
        if login == CODEX_APP:
            bodies = [review.get("body") or ""] + list(review_comments.get(review.get("id"), []))
            blocking = any(BLOCKING_FINDING_RE.search(b) for b in bodies)
            out.append((at, commit, "FAIL" if blocking else "PASS"))
        elif login.lower() in allowed and review.get("state") == "COMMENTED":
            verdict = first_line_verdict(review.get("body"))
            if verdict:
                out.append((at, commit, verdict))
    if head_pushed_at:
        for reaction in reactions:
            login = (reaction.get("user") or {}).get("login")
            at = reaction.get("created_at") or ""
            if login == CODEX_APP and reaction.get("content") == "+1" and at >= head_pushed_at:
                out.append((at, head, "PASS"))
    return sorted(out, key=lambda v: v[0])


def evaluate(pr, files, found, same_change):
    """Return (ok, reasons). found is verdicts(); same_change(sha) -> True when sha's net change equals head's."""
    reasons = []
    head = (pr.get("head") or {}).get("sha")
    labels = {label.get("name") for label in pr.get("labels") or []}
    if pr.get("draft"):
        reasons.append("PR is a draft")
    if files is None:
        reasons.append("changed-file list unavailable or too long")
        files = []
    if not found:
        reasons.append("no independent review yet (Codex GitHub app review, "
                       "or `@codex review` and its thumbs-up)")
    else:
        _, commit, verdict = found[-1]
        if verdict == "FAIL":
            reasons.append(f"latest independent review has a P0/P1 finding or FAIL "
                           f"(on {str(commit)[:12]})")
        elif commit != head and not same_change(commit):
            reasons.append(f"review is on {str(commit)[:12]}, not the current head "
                           f"{str(head)[:12]}, and the change differs: ask `@codex review`")
    held = needs_jeremy(files)
    if held and APPROVAL_LABEL not in labels:
        reasons.append(f"value math or a migration changes ({', '.join(held[:5])}): "
                       f"needs Jeremy's yes (`{APPROVAL_LABEL}` label)")
    if HANDOFF in files and HANDOFF_LABEL not in labels:
        reasons.append(f"edits {HANDOFF}; put notes in docs/claude-log or Linear "
                       f"(or `{HANDOFF_LABEL}` label for a deliberate edit)")
    return not reasons, reasons


def _pages(fetch_api, path):
    out, page = [], 1
    while True:
        joiner = "&" if "?" in path else "?"
        batch = fetch_api(f"{path}{joiner}per_page=100&page={page}")
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1


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
    number = (payload.get("pull_request") or {}).get("number")
    if not number:
        return False, [f"{event_name or 'unknown'} event names no pull request"]
    if fetch_api is None:
        repo, token = environ.get("GITHUB_REPOSITORY"), environ.get("GH_TOKEN")

        def fetch_api(api_path):
            if not repo or not token:
                raise ValueError("repository or token unavailable")
            return _api(f"repos/{repo}/{api_path}", token)

    reviewers = [r.strip() for r in (environ.get("DDF_REVIEW_LOGINS") or "").split(",")]
    try:
        pr = fetch_api(f"pulls/{number}")
        head = (pr.get("head") or {}).get("sha")
        files = file_names(_pages(fetch_api, f"pulls/{number}/files"))
        if len(files) >= FILE_LIMIT:
            files = None
        reviews = _pages(fetch_api, f"pulls/{number}/reviews")
        review_comments = {
            r["id"]: [c.get("body") or "" for c in
                      _pages(fetch_api, f"pulls/{number}/reviews/{r['id']}/comments")]
            for r in reviews if (r.get("user") or {}).get("login") == CODEX_APP}
        # The app's thumbs-up lands on the PR itself or on the `@codex review`
        # comment that asked for it.
        reactions = _pages(fetch_api, f"issues/{number}/reactions")
        for comment in _pages(fetch_api, f"issues/{number}/comments"):
            if "@codex review" in (comment.get("body") or "").lower():
                reactions += _pages(fetch_api, f"issues/comments/{comment['id']}/reactions")
        suites = fetch_api(f"commits/{head}/check-suites?per_page=100").get("check_suites") or []
    except Exception as error:  # noqa: BLE001 - fail closed
        return False, [f"GitHub API unavailable ({type(error).__name__})"]

    # When the head was pushed: its first check suite. Without it, a reaction
    # cannot be tied to this head and does not count.
    pushed = min((s.get("created_at") for s in suites if s.get("created_at")), default=None)
    author = (pr.get("user") or {}).get("login")
    found = verdicts(reviews, review_comments, reactions, head, pushed, author, reviewers)
    base = (pr.get("base") or {}).get("sha")

    def same_change(sha):
        if not sha or not head or not base:
            return False
        try:
            then = net_change(fetch_api(f"compare/{base}...{sha}"))
            now = net_change(fetch_api(f"compare/{base}...{head}"))
        except Exception:  # noqa: BLE001 - doubt means re-review
            return False
        return bool(now) and then is not None and then == now

    return evaluate(pr, files, found, same_change)


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
