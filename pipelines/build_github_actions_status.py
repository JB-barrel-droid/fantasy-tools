#!/usr/bin/env python3
"""Build GitHub Actions workflow status for the monitoring dashboard.

Fetches all workflows in the repo, their recent run history (last 5 runs
each with times, conclusions, and durations), and maps each to the
pipeline stage it covers. Outputs dist/modules/github-actions.json.

Per-run and per-workflow fields (JEG-109):
  - run.duration_s         wall-clock seconds from created_at to updated_at
  - workflow.consecutive_failures
                           count back from the most recent run; stop at the
                           first non-failure (success, cancelled, in_progress,
                           skipped, or null conclusion). Distinct from
                           recent_failures (last-5 failure count).
  - workflow.last_success_at
                           ISO timestamp of the most recent run with
                           conclusion == "success"; null if none in the window.
  - workflow.failing_streak alert flag: consecutive_failures >=
                           FAILING_STREAK_THRESHOLD. Threshold of 3 would
                           have flagged the 5-consecutive-failure JEG-113
                           outage two runs before it stopped the chain.
  - workflow.alert_needed  (JEG-313) Same predicate as failing_streak
                           (consecutive_failures >= FAILING_STREAK_THRESHOLD);
                           kept as a separate field so the dashboard can
                           show a distinct "alert: failing streak" badge
                           without conflating the two signals.

Pipeline coverage map:
  - Rebuild comparison chain: C1-C8 (import -> health -> comparison rebuild)
  - FantasyCalc drift check and refresh: FantasyCalc source freshness
  - Deploy dashboard: C9-C10 (Pages deploy + rendered output)

Usage:
  python3 pipelines/build_github_actions_status.py [--out dist/modules/github-actions.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "JB-barrel-droid/fantasy-tools"

# A failing streak this long or longer is a deploy-blocking alert. JEG-113
# was a 5-run outage on "Rebuild comparison chain"; the threshold of 3
# would have surfaced it two runs earlier (per JEG-109 brief).
FAILING_STREAK_THRESHOLD = 3

# Map workflow names to pipeline coverage
PIPELINE_COVERAGE = {
    "Rebuild comparison chain": {
        "stages": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"],
        "description": "Import snapshots from Supabase, health check, rebuild comparison chain",
        "schedule": "On vintage change (hourly source-vintage-check dispatches it; JEG-76)",
        "key_task": "Automated pipeline refresh",
    },
    "FantasyCalc drift check and refresh": {
        "stages": ["Source freshness"],
        "description": "Check FantasyCalc live values vs stored, trigger refresh on drift",
        "schedule": "Scheduled (check workflow file)",
        "key_task": "FantasyCalc source freshness",
    },
    "Deploy dashboard": {
        "stages": ["C9", "C10"],
        "description": "Deploy dist/ to GitHub Pages",
        "schedule": "On push to main",
        "key_task": "Production deployment",
    },
    "ESPN scrape to Supabase": {
        "stages": ["Source ingest"],
        "description": "Scrape fresh ESPN projections and save to Supabase",
        "schedule": "Daily at 11:30 UTC (06:30 CT)",
        "key_task": "ESPN scrape to Supabase",
    },
    "Rebuild player trace": {
        "stages": ["Player Trace"],
        "description": "Rebuild player trace artifact from latest pipeline data",
        "schedule": "Every 6 hours (47 */6 * * *)",
        "key_task": "Player Trace rebuild",
    },
    "Source vintage check": {
        "stages": ["C1"],
        "description": "Hourly DB-vs-fixture vintage comparison; dispatches the rebuild chain on change",
        "schedule": "Hourly (JEG-76)",
        "key_task": "Vintage-gated rebuild trigger",
    },
}


def fetch_json(url: str) -> dict:
    """Fetch JSON from GitHub API (unauthenticated, rate-limited)."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "fantasy-tools-monitor/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp into a tz-aware datetime, or None."""
    if not ts:
        return None
    try:
        # GitHub returns "...Z"; datetime.fromisoformat wants +00:00 in 3.10
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_duration_s(run: dict) -> int | None:
    """Wall-clock seconds from created_at to updated_at for a single run.

    Returns None if either timestamp is missing or unparseable. GitHub
    occasionally re-queues a run, which can make updated_at < created_at;
    in that case we return 0 rather than a negative number so the duration
    field is always a non-negative integer or null.
    """
    start = _parse_iso(run.get("created_at"))
    end = _parse_iso(run.get("updated_at"))
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    return max(0, int(delta))


def consecutive_failures(runs: list[dict]) -> int:
    """Count consecutive failures back from the most recent run.

    A run counts as a failure only when its conclusion is exactly
    "failure". Cancelled, skipped, in_progress, queued, and runs with a
    null conclusion all break the streak (they are not the same as a
    confirmed failure). The streak stops at the first non-failure.

    This is intentionally different from `recent_failures`, which counts
    every failure in the last 5 runs regardless of position. A single
    old failure with four recent successes is recent_failures=1 but
    consecutive_failures=0 — and that is correct, because the chain is
    not currently broken.
    """
    count = 0
    for r in runs:
        if r.get("conclusion") == "failure":
            count += 1
        else:
            break
    return count


def last_success_at(runs: list[dict]) -> str | None:
    """ISO timestamp of the most recent run with conclusion == "success",
    or None if no run in the window succeeded. Returned as the raw
    created_at string from GitHub so the dashboard can localise the
    display with timeAgo() without re-parsing."""
    for r in runs:
        if r.get("conclusion") == "success":
            return r.get("created_at")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(ROOT / "dist" / "modules" / "github-actions.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)

    # Fetch workflows
    workflows_data = fetch_json(
        f"https://api.github.com/repos/{REPO}/actions/workflows"
    )

    workflows = []
    for wf in workflows_data.get("workflows", []):
        wf_id = wf["id"]
        wf_name = wf["name"]

        # Fetch recent runs (last 5) — JEG-109: track run history, not just latest
        runs_data = fetch_json(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{wf_id}/runs?per_page=5"
        )
        runs = runs_data.get("workflow_runs", [])
        recent_runs = [
            {
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "event": r.get("event"),
                "html_url": r.get("html_url"),
                "duration_s": run_duration_s(r),
            }
            for r in runs
        ]
        last_run = recent_runs[0] if recent_runs else None

        # Health signal: ok if last run succeeded (or is in progress);
        # warn if last run failed but an earlier recent run succeeded;
        # fail if all recent runs failed or no runs exist.
        conclusions = [r["conclusion"] for r in recent_runs if r["conclusion"]]
        if not recent_runs:
            health = "unknown"
        elif last_run and last_run["conclusion"] == "success":
            health = "ok"
        elif last_run and last_run["status"] in ("in_progress", "queued"):
            health = "running"
        elif "success" in conclusions:
            health = "warn"
        else:
            health = "fail"

        # Streak / last-success signal (JEG-109): count back from the latest
        # run, stop at the first non-failure. failing_streak is the alert
        # flag that would have caught the JEG-113 5-run outage at run 3.
        streak = consecutive_failures(recent_runs)
        success_ts = last_success_at(recent_runs)

        coverage = PIPELINE_COVERAGE.get(wf_name, {
            "stages": ["Unknown"],
            "description": "No coverage mapping defined",
            "schedule": "Unknown",
            "key_task": "Unmapped",
        })

        workflows.append({
            "id": wf_id,
            "name": wf_name,
            "path": wf.get("path", ""),
            "state": wf.get("state", "unknown"),
            "coverage": coverage,
            "health": health,
            "last_run": last_run,
            "recent_runs": recent_runs,
            "recent_failures": sum(1 for c in conclusions if c == "failure"),
            "consecutive_failures": streak,
            "last_success_at": success_ts,
            "failing_streak": streak >= FAILING_STREAK_THRESHOLD,
            # JEG-313: per-workflow alert flag. Same threshold as
            # failing_streak (consecutive_failures >= FAILING_STREAK_THRESHOLD).
            # This is the well-scoped part of the dispatch: the pipeline
            # surfaces alert_needed on each workflow so the dashboard can
            # show a badge. The actual alert destination (Slack, GitHub
            # Issue, etc.) is a separate dispatch owned by Roman.
            "alert_needed": streak >= FAILING_STREAK_THRESHOLD,
        })

    # Check for coverage gaps
    all_stages = set()
    for wf in workflows:
        all_stages.update(wf["coverage"]["stages"])

    # Key tasks that should have automation
    required_tasks = [
        "Automated pipeline refresh",
        "FantasyCalc source freshness",
        "Production deployment",
        "ESPN scrape to Supabase",  # Currently manual/cron, not GitHub Action
        "Player Trace rebuild",  # May be manual
    ]

    covered_tasks = {wf["coverage"]["key_task"] for wf in workflows}
    gaps = [t for t in required_tasks if t not in covered_tasks]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": REPO,
        "workflows": workflows,
        "coverage_gaps": gaps,
        "summary": {
            "total_workflows": len(workflows),
            "active": sum(1 for w in workflows if w["state"] == "active"),
            "healthy": sum(1 for w in workflows if w["health"] == "ok"),
            "warn": sum(1 for w in workflows if w["health"] == "warn"),
            "failing": sum(1 for w in workflows if w["health"] == "fail"),
            "running": sum(1 for w in workflows if w["health"] == "running"),
            "failing_streak_count": sum(1 for w in workflows if w.get("failing_streak")),
            # JEG-313: mirror of failing_streak_count at the summary level so the
            # dashboard can render an aggregate badge without re-counting.
            "alert_needed_count": sum(1 for w in workflows if w.get("alert_needed")),
            "max_consecutive_failures": max((w.get("consecutive_failures", 0) for w in workflows), default=0),
            "gaps_count": len(gaps),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {out_path} ({len(workflows)} workflows, {len(gaps)} gaps)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
