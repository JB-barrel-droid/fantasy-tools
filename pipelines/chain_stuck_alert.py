#!/usr/bin/env python3
"""Open one GitHub issue when the board stops publishing (JEG-1194).

From 2026-10-26 15:42Z the rebuild chain failed every run for about 44 hours.
Each run recorded the failure in comparison-chain-status.json and in the
monitoring table, and the job went red, but nothing reached Jeremy: the board
sat on week 7 while every source had week 8 in Supabase.

    python3 pipelines/chain_stuck_alert.py --chain-outcome failure|success

Runs at the end of rebuild-chain.yml on main. When the chain failed and the
published fixture is older than STUCK_HOURS, it opens one issue labelled
`chain-stuck` (or comments on the open one, at most once per COMMENT_HOURS)
naming the failing check, the held sources and the week each source serves.
When the chain succeeds it closes the open issue. GitHub emails the repository
owner for both. Without GITHUB_TOKEN it prints what it would do. It never
fails the job: the alert is a warning, like every other staleness signal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
from lib.timestamps import parse_iso_timestamp  # noqa: E402

STATUS = REPO / "output" / "comparison-chain-status.json"
HISTORY = REPO / "data" / "history" / "index.json"
LABEL = "chain-stuck"
TITLE = "The board has stopped publishing"
STUCK_HOURS = 6
COMMENT_HOURS = 6
API = "https://api.github.com"


def _parse(ts) -> datetime | None:
    try:
        dt = parse_iso_timestamp(str(ts))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hours_since(ts, now: datetime) -> float | None:
    dt = _parse(ts)
    return None if dt is None else (now - dt).total_seconds() / 3600


def decide(chain_outcome: str, built_at, now: datetime) -> str:
    """'open' (stuck), 'close' (published) or 'none' (failed, not stuck yet)."""
    if chain_outcome == "success":
        return "close"
    if chain_outcome != "failure":
        return "none"  # skipped or cancelled: says nothing either way
    age = hours_since(built_at, now)
    return "open" if age is None or age >= STUCK_HOURS else "none"


def body(status: dict, history: dict, now: datetime) -> str:
    built = history.get("fixture_built_at")
    age = hours_since(built, now)
    prv = status.get("post_rebuild_validation") or {}
    failing = prv.get("failed_tests") or ([prv["detail"]] if prv.get("detail") else [])
    lines = [
        f"The rebuild chain has not published since {built or 'an unknown time'}"
        + (f" ({age:.0f} hours ago)." if age is not None else "."),
        "",
        "Failing check: " + ("; ".join(failing) if failing else
                             (status.get("detail") or "see the run log")),
    ]
    held = status.get("held") or []
    if held:
        lines.append("Held sources: " + ", ".join(sorted(held)))
    served = history.get("served") or {}
    if served:
        lines += ["", "Week each source serves on the site:"]
        lines += [f"- {src}: week {(info or {}).get('week')}" for src, info in sorted(served.items())]
    weeks = status.get("source_weeks") or {}
    if weeks:
        lines += ["", "Week each source reached in the failed run:"]
        lines += [f"- {src}: week {wk.get('served_week') if isinstance(wk, dict) else wk}"
                  for src, wk in sorted(weeks.items())]
    run = os.environ.get("GITHUB_RUN_ID")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if run and repo:
        lines += ["", f"Latest run: https://github.com/{repo}/actions/runs/{run}"]
    lines += ["", "This issue closes itself when the chain next publishes (JEG-1194)."]
    return "\n".join(lines)


def _call(method: str, path: str, token: str, payload: dict | None = None):
    req = urllib.request.Request(
        API + path, method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def open_issue(repo: str, token: str, call=_call) -> dict | None:
    issues = call("GET", f"/repos/{repo}/issues?state=open&labels={LABEL}&per_page=10", token) or []
    issues = [i for i in issues if "pull_request" not in i]
    return issues[0] if issues else None


def run(action: str, text: str, repo: str | None, token: str | None, now: datetime, call=None) -> str:
    """Carry out the action; returns what was done (for the log and tests)."""
    if action == "none":
        return "nothing to do"
    if not token or not repo:
        return f"dry run: would {action} the {LABEL} issue\n{text if action == 'open' else ''}".rstrip()
    call = call or _call
    issue = open_issue(repo, token, call)
    if action == "close":
        if not issue:
            return "published; no open issue"
        call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token,
             {"body": "The chain published again, so this is resolved."})
        call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token,
             {"state": "closed", "state_reason": "completed"})
        return f"closed #{issue['number']}"
    if issue is None:
        made = call("POST", f"/repos/{repo}/issues", token,
                    {"title": TITLE, "body": text, "labels": [LABEL]})
        return f"opened #{made['number']}"
    since = hours_since(issue.get("updated_at"), now)
    if since is not None and since < COMMENT_HOURS:
        return f"#{issue['number']} already open; updated {since:.1f} h ago"
    call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token, {"body": text})
    return f"commented on #{issue['number']}"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chain-outcome", required=True)
    ap.add_argument("--status", default=str(STATUS))
    ap.add_argument("--history", default=str(HISTORY))
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    status, history = _read(Path(args.status)), _read(Path(args.history))
    action = decide(args.chain_outcome, history.get("fixture_built_at"), now)
    try:
        done = run(action, body(status, history, now), os.environ.get("GITHUB_REPOSITORY"),
                   os.environ.get("GITHUB_TOKEN"), now)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(f"::warning title=chain stuck alert::could not reach GitHub issues ({type(e).__name__}: {e})")
        return 0
    if action == "open":
        print(f"::warning title=Board not publishing::{done}")
    else:
        print(f"chain stuck alert: {done}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
