#!/usr/bin/env python3
"""Compare config/monitoring_coverage.json with the live monitoring summary.

Offline checks (workflows vs manifest) live in tests/test_monitoring_coverage.py.
This one catches drift that only exists in Supabase: a pg_cron job nobody mapped
to a check, a check_config row with no manifest entry, or a manifest check that
was never inserted. It reads the summary snapshot that
pipelines/build_monitoring_summary.py wrote (checks + cron_jobs from
public.monitoring_summary()), so it needs no database access of its own.

    python3 pipelines/audit_monitoring_coverage.py output/monitoring-summary.json

Exit 1 on any gap; each gap is printed as an ::error annotation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "monitoring_coverage.json"

# pg_cron jobs that are plumbing for the monitor or covered through another job.
# Anything else active in cron.job must be in the manifest.


def manifest_sets(manifest):
    checks, jobs = set(), set()
    for p in manifest["pipelines"]:
        if p.get("pg_cron_job"):
            jobs.add(p["pg_cron_job"])
        for r in p["records"]:
            checks.add(r["check_id"])
    for j in manifest["pg_cron_sql_jobs"]:
        jobs.add(j["jobname"])
        checks.add(j["check_id"])
    return checks, jobs


def audit(manifest, summary):
    """Return a list of human-readable gaps (empty = full coverage)."""
    gaps = []
    want_checks, want_jobs = manifest_sets(manifest)
    have_checks = {c["check_id"] for c in summary.get("checks", [])}
    have_jobs = {j["jobname"] for j in summary.get("cron_jobs", []) if j.get("active", True)}
    for c in sorted(want_checks - have_checks):
        gaps.append(f"check {c} is in the manifest but has no monitoring.check_config row")
    for c in sorted(have_checks - want_checks):
        gaps.append(f"check {c} exists in monitoring.check_config but not in the manifest")
    for j in sorted(have_jobs - want_jobs):
        gaps.append(f"pg_cron job {j} is active but has no manifest entry (no check proves it ran)")
    for j in sorted(want_jobs - have_jobs):
        gaps.append(f"pg_cron job {j} is in the manifest but not active in cron.job")
    return gaps


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    summary = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    if summary.get("read_error"):
        print(f"::warning title=coverage-audit::skipped, monitor unreadable: {summary['read_error']}")
        return 0
    gaps = audit(manifest, summary)
    for g in gaps:
        print(f"::error title=monitoring-coverage::{g}")
    print(f"monitoring coverage: {len(gaps)} gap(s)")
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
