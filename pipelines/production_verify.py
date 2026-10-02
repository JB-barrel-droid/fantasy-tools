#!/usr/bin/env python3
"""Production verifier: check workflow runs and Supabase table state.

Queries GitHub Actions API for the latest workflow run and Supabase for the
current row count and vintage, then compares against local snapshots.
Writes output/production-verify.json with verification state per workflow.

Usage:
    python3 pipelines/production_verify.py [--help]

GitHub API: uses unauthenticated public API (rate-limited to 60 requests/hour).
Supabase: read-only via sbclient (pipelines/gh_sbclient.py).

State values:
    - verified: run green + table matches local snapshot
    - never_run: no run since merge
    - run_failed: last run not green
    - mismatch: run green but table doesn't match snapshot
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = "JB-barrel-droid/fantasy-tools"

# Workflow registry: maps workflow file name to its verification config.
# Add new workflows here (one line each).
WORKFLOWS = {
    "cbsros-supabase-sync.yml": {
        "table": "cbs_ros_projections",
        "vintage_column": "cbs_snapshot_date",
        "snapshot_source": "cbsros",
    },
}


def fetch_json(url: str) -> dict:
    """Fetch JSON from GitHub API (unauthenticated, rate-limited)."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "fantasy-tools-production-verify/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_latest_workflow_run(workflow_name: str) -> dict | None:
    """Fetch the most recent run for a workflow.

    Returns dict with keys: created_at, status, conclusion, or None if no runs.
    """
    # First, get the workflow ID by listing workflows
    try:
        workflows_data = fetch_json(
            f"https://api.github.com/repos/{REPO}/actions/workflows"
        )
    except Exception as e:
        print(f"Warning: failed to fetch workflows: {e}", file=sys.stderr)
        return None

    workflow_id = None
    for wf in workflows_data.get("workflows", []):
        if wf.get("path") == f".github/workflows/{workflow_name}":
            workflow_id = wf["id"]
            break

    if workflow_id is None:
        return None

    # Get the most recent run for this workflow
    try:
        runs_data = fetch_json(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow_id}/runs?per_page=1"
        )
        runs = runs_data.get("workflow_runs", [])
        if not runs:
            return None
        run = runs[0]
        return {
            "created_at": run.get("created_at"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
        }
    except Exception as e:
        print(f"Warning: failed to fetch runs for {workflow_name}: {e}", file=sys.stderr)
        return None


def get_latest_snapshot(source: str) -> dict | None:
    """Read the latest snapshot for a source from data/raw/sources/<source>/.

    Returns dict with keys: row_count, vintage (from directory name), or None.
    """
    snapshot_dir = ROOT / "data" / "raw" / "sources" / source
    if not snapshot_dir.exists():
        return None

    # Find the latest vintage directory (lexicographic = chronological)
    vintage_dirs = sorted([d for d in snapshot_dir.iterdir() if d.is_dir()], reverse=True)
    if not vintage_dirs:
        return None

    latest_dir = vintage_dirs[0]
    snapshot_file = latest_dir / "snapshot.json"
    if not snapshot_file.exists():
        return None

    try:
        data = json.loads(snapshot_file.read_text())
        return {
            "row_count": data.get("row_count", 0),
            "vintage": latest_dir.name,  # directory name is the vintage date
        }
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: failed to read snapshot for {source}: {e}", file=sys.stderr)
        return None


def get_table_state(table: str, vintage_column: str) -> dict | None:
    """Query Supabase for the table's latest state.

    Returns dict with keys: row_count, latest_vintage, or None on error.
    Requires SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables.
    """
    # Import sbclient dynamically to get the standalone version
    sys.path.insert(0, str(ROOT / "pipelines"))
    try:
        import gh_sbclient as sbclient
    except ImportError:
        print("Error: sbclient not available", file=sys.stderr)
        return None

    try:
        # Get count and latest vintage
        # Use select=*,count=exact for row count
        params_count = f"?select=*,count=exact&order={vintage_column}.desc.nullslast&limit=1"

        # First get the count
        rows = sbclient.get_all(table, params="?select=*", batch=1000)

        if rows is None:
            return None

        row_count = len(rows)

        # Get the latest vintage from the most recent row
        latest_vintage = None
        if rows:
            # Sort by vintage column descending to get latest
            sorted_rows = sorted(
                rows,
                key=lambda r: r.get(vintage_column) or "",
                reverse=True
            )
            latest_vintage = sorted_rows[0].get(vintage_column)

        return {
            "row_count": row_count,
            "latest_vintage": latest_vintage,
        }
    except Exception as e:
        print(f"Warning: failed to query table {table}: {e}", file=sys.stderr)
        return None


def determine_state(run_info: dict | None, table_info: dict | None, snapshot_info: dict | None) -> str:
    """Determine the verification state based on run, table, and snapshot info.

    State logic:
    - never_run: no run exists (run_info is None)
    - run_failed: run exists but conclusion is not "success"
    - mismatch: run is green but table doesn't match snapshot
    - verified: run is green AND table matches snapshot
    """
    # No run at all
    if run_info is None:
        return "never_run"

    # Run exists but failed
    conclusion = run_info.get("conclusion")
    if conclusion != "success":
        return "run_failed"

    # Run succeeded - check snapshot match
    if table_info is None or snapshot_info is None:
        # If we can't get table or snapshot info, assume mismatch
        return "mismatch"

    table_count = table_info.get("row_count")
    snapshot_count = snapshot_info.get("row_count")
    table_vintage = table_info.get("latest_vintage")
    snapshot_vintage = snapshot_info.get("vintage")

    # Both count and vintage must match
    if table_count == snapshot_count and table_vintage == snapshot_vintage:
        return "verified"

    return "mismatch"


def verify_workflow(workflow_name: str, config: dict) -> dict:
    """Verify a single workflow.

    Returns dict with keys: last_run_at, last_run_status, table_row_count,
    snapshot_match, state.
    """
    # Get latest run from GitHub
    run_info = get_latest_workflow_run(workflow_name)

    # Get local snapshot info
    snapshot_info = get_latest_snapshot(config["snapshot_source"])

    # Get table state from Supabase
    table_info = get_table_state(config["table"], config["vintage_column"])

    # Determine state
    state = determine_state(run_info, table_info, snapshot_info)

    # Compute snapshot_match
    snapshot_match = False
    if table_info and snapshot_info:
        snapshot_match = (
            table_info.get("row_count") == snapshot_info.get("row_count")
            and table_info.get("latest_vintage") == snapshot_info.get("vintage")
        )

    return {
        "last_run_at": run_info.get("created_at") if run_info else None,
        "last_run_status": run_info.get("conclusion") if run_info else None,
        "table_row_count": table_info.get("row_count") if table_info else None,
        "snapshot_match": snapshot_match,
        "state": state,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify production workflows against GitHub Actions and Supabase"
    )
    parser.add_argument(
        "--workflow",
        help="Verify only this workflow (default: verify all)",
    )
    args = parser.parse_args()

    # Check for required environment variables early (fail closed)
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        # This is not a hard error - we can still verify GitHub-only
        print(
            "Warning: SUPABASE_URL or SUPABASE_SERVICE_KEY not set; "
            "Supabase checks will be skipped",
            file=sys.stderr
        )

    workflows_to_check = (
        {args.workflow: WORKFLOWS[args.workflow]}
        if args.workflow
        else WORKFLOWS
    )

    results = {}
    for workflow_name, config in workflows_to_check.items():
        results[workflow_name] = verify_workflow(workflow_name, config)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflows": results,
    }

    out_path = ROOT / "output" / "production-verify.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
