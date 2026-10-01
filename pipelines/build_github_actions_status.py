#!/usr/bin/env python3
"""Build GitHub Actions workflow status for the monitoring dashboard.

Fetches all workflows in the repo, their last run status, and maps each
to the pipeline stage it covers. Outputs dist/modules/github-actions.json.

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
        "schedule": "Every 6 hours (17 */6 * * *)",
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

        # Fetch last run
        runs_data = fetch_json(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{wf_id}/runs?per_page=1"
        )
        runs = runs_data.get("workflow_runs", [])
        last_run = runs[0] if runs else None

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
            "last_run": {
                "created_at": last_run.get("created_at") if last_run else None,
                "status": last_run.get("status") if last_run else None,
                "conclusion": last_run.get("conclusion") if last_run else None,
                "event": last_run.get("event") if last_run else None,
                "html_url": last_run.get("html_url") if last_run else None,
            } if last_run else None,
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
            "failing": sum(
                1 for w in workflows
                if w["last_run"] and w["last_run"]["conclusion"] == "failure"
            ),
            "gaps_count": len(gaps),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {out_path} ({len(workflows)} workflows, {len(gaps)} gaps)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
