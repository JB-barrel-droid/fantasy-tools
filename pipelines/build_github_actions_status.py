#!/usr/bin/env python3
"""Build GitHub Actions workflow status for the monitoring dashboard.

Fetches all workflows in the repo, their recent run history (last 5 runs
each with times and conclusions), and maps each to the pipeline stage it
covers. Outputs dist/modules/github-actions.json.

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
            "gaps_count": len(gaps),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {out_path} ({len(workflows)} workflows, {len(gaps)} gaps)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
