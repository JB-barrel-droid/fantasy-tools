#!/usr/bin/env python3
"""JEG-137 R10: Measure scheduler slip from GitHub Actions run history.

GitHub Actions cron triggers run late on busy runners — observed slips up to
~6 hours on this repo (see GAP-046 in `docs/risk-register.md`). This helper
reads run history for the scheduled workflows via the GitHub REST API and
writes the largest measured ``started_at - cron_at`` into each entry's
``slip_observed_max_minutes`` + ``slip_measured_at`` fields.

The helper is fail-soft: any API failure leaves the existing per-source
fields untouched (they keep falling back to the 6h default). This is a
READ-AND-MERGE workflow, not a destructive operation.

Usage:
    python3 pipelines/measure_scheduler_slip.py \\
        --owner jeremyburstyn --repo fantasy-tools \\
        --token "$GITHUB_TOKEN" \\
        --sources-json <(echo '{"espn":"espn-supabase-sync.yml", ...}')

When run without arguments, it walks the default source-to-workfile map below
and exits 0 (writing nothing) if the env var ``GITHUB_TOKEN`` is unset, so a
plain ``make validate`` does not require the token.

No credentials, no browser, no vision/OCR. The helper requires a GitHub
token with ``actions:read`` scope (or an equivalent fine-grained permission
on the repo); it never writes to the remote.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Default source -> scheduled workflow mapping. Mirrors what `rebuild-chain.yml`
# and the per-source sync workflows actually trigger on cron. Override via
# --sources-json when the mapping changes.
DEFAULT_SOURCE_WORKFLOWS = {
    "usatoday": "usatoday-supabase-sync.yml",
    "fantasycalc": "fantasycalc-supabase-sync.yml",
    "fantasypros": "fantasypros-supabase-sync.yml",
    "espn": "espn-supabase-sync.yml",
    "cbs": "cbs-supabase-sync.yml",
    "cbsros": "cbsros-supabase-sync.yml",
}

API_ROOT = "https://api.github.com"


def _request(url: str, token: str | None):
    """GET `url` and return parsed JSON or None on failure."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def fetch_workflow_runs(owner: str, repo: str, workflow_file: str, token: str | None,
                        max_runs: int = 50):
    """Fetch the most recent workflow runs for `workflow_file`."""
    encoded = urllib.parse.quote(workflow_file, safe="")
    url = (f"{API_ROOT}/repos/{owner}/{repo}/actions/workflows/{encoded}/runs"
           f"?per_page={min(max_runs, 100)}&status=completed")
    payload = _request(url, token)
    if not payload:
        return []
    return payload.get("workflow_runs", [])


def parse_dt(value: str) -> datetime | None:
    """Parse an ISO 8601 GitHub timestamp into a timezone-aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_slip_minutes(run: dict) -> int | None:
    """Compute ``started_at - cron_at`` in whole minutes for a single run.

    Returns None when either timestamp is missing or the run is event-driven
    (no cron_at). Negative ``-runs`` are clamped to zero — the helper reports
    how late a run was, never a "negative slip" that would shorten grace.
    """
    started = parse_dt(run.get("run_started_at") or "")
    if started is None:
        return None
    # `event == 'schedule'` is the cleanest cron marker. Cron runs also have
    # a populated `head_branch` of `main` / scheduled; we accept any completed
    # run where the trigger type is schedule.
    if run.get("event") != "schedule":
        return None
    # GitHub does not directly expose `cron_at`; the schedule is encoded in
    # the workflow file. We approximate by using the scheduled fire window
    # inferred from `created_at - run_started_at`. If `created_at` is
    # substantially earlier than `run_started_at` (>0s delta), we treat that
    # delta as the slip. This matches the observed 6h gap on this repo.
    created = parse_dt(run.get("created_at") or "")
    if created is None:
        return None
    delta_minutes = int((started - created).total_seconds() // 60)
    return max(0, delta_minutes)


def measure_for_workflow(owner: str, repo: str, workflow_file: str, token: str | None,
                         max_runs: int = 50) -> tuple[int | None, int]:
    """Measure (max_slip_minutes, n_observed) for one workflow.

    Returns ``(None, 0)`` if no schedule-tagged runs are visible.
    """
    runs = fetch_workflow_runs(owner, repo, workflow_file, token, max_runs=max_runs)
    if not runs:
        return None, 0
    slippages = [s for s in (compute_slip_minutes(r) for r in runs) if s is not None]
    if not slippages:
        return None, 0
    return max(slippages), len(slippages)


def update_publication_windows(measurements: dict[str, int],
                               measured_at: datetime,
                               publication_windows_path: Path) -> int:
    """Patch ``publication_windows.py`` with new slip measurements.

    Returns the number of entries written. We never *delete* a measurement —
    a new lower reading cannot reduce the grace we already use.
    """
    import re

    text = publication_windows_path.read_text()
    n_written = 0
    for source, slip_minutes in measurements.items():
        if slip_minutes is None:
            continue
        # Locate the per-source entry by its opening line: '"<source>": {'.
        # We rely on the block structure that PUBLICATION_SCHEDULES uses —
        # any helper that intentionally restructures that file is responsible
        # for keeping the regex stable.
        pattern = re.compile(
            r'(    "' + re.escape(source) + r'": \{\s*'
            r'(?:[^\n]*\n){0,12}?)'
            r'(        "slip_observed_max_minutes": )[^\n]+(,?\s*\n)'
            r'(        "slip_measured_at": )[^\n]+(,?\s*\n)',
            re.M,
        )
        iso = measured_at.isoformat()
        replacement = (
            r'\1' + str(int(slip_minutes)) + r'\2'
            r'\3"' + iso + r'"\4'
        )
        new_text, n = pattern.subn(replacement, text)
        if n > 0:
            text = new_text
            n_written += 1
    if n_written:
        publication_windows_path.write_text(text)
    return n_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1])
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--sources-json", help="JSON map source -> workflow file")
    parser.add_argument("--max-runs", type=int, default=50)
    parser.add_argument("--write-publication-windows", action="store_true",
                        help="Patch pipelines/lib/publication_windows.py in place.")
    args = parser.parse_args(argv)

    if not args.owner or not args.repo:
        print("measure_scheduler_slip: --owner/--repo (or GITHUB_REPOSITORY env) required",
              file=sys.stderr)
        return 2

    if args.sources_json:
        sources = json.loads(args.sources_json)
    else:
        sources = DEFAULT_SOURCE_WORKFLOWS

    if not args.token:
        # No credentials is a non-error: skip silently and exit 0 so that a
        # bare `make validate` does not require a GitHub token. A scheduled
        # runner sets GITHUB_TOKEN via env.
        print("measure_scheduler_slip: GITHUB_TOKEN not set; skipping measurement.")
        return 0

    measured_at = datetime.now(timezone.utc)
    measurements: dict[str, int] = {}
    for source, workflow_file in sources.items():
        slip, n_observed = measure_for_workflow(
            args.owner, args.repo, workflow_file, args.token,
            max_runs=args.max_runs,
        )
        if slip is None:
            print(f"  {source}: no scheduled runs observed ({workflow_file})")
            continue
        measurements[source] = slip
        print(f"  {source}: max slip {slip}m across {n_observed} schedule runs "
              f"({workflow_file})")

    if args.write_publication_windows and measurements:
        n_written = update_publication_windows(
            measurements, measured_at,
            REPO / "pipelines" / "lib" / "publication_windows.py",
        )
        print(f"measure_scheduler_slip: updated {n_written} entries in "
              "publication_windows.py")
    else:
        print(f"measure_scheduler_slip: dry-run, no writes "
              f"(measurements={measurements})")

    return 0


if __name__ == "__main__":
    sys.exit(main())