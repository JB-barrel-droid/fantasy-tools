#!/usr/bin/env python3
"""JEG-414 (ARCH-013): independent freshness watch for the health artifacts.

JEG-414 follow-up: artifacts are now stored in Supabase public.ops_artifacts
(was: committed to main as dist/modules/*.json). The watch reads them from
Supabase via service_role (CI) or anon key (browser). The staleness check
and Supabase observation recording are unchanged.

  * fetches each artifact from Supabase and measures the age of its own
    timestamp (generated_at / checked_at) -- never HTTP Last-Modified or
    fetch time;
  * records one observation per artifact into Supabase
    monitoring.check_observations via public.monitoring_record_observation
    (the pg_cron evaluator marks the check 'missed' if this workflow itself
    stops reporting);
  * exits 1 when any artifact is older than MAX_AGE_MINUTES (red).

Fail-closed: an unreachable artifact, unparseable JSON or a missing
timestamp is stale, never fresh.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_AGE_MINUTES = 60  # twice the 30-minute heartbeat (BH-8)
OWNER = "health-artifacts.yml"

ARTIFACTS = {
    # check_id: (ops_artifacts name, timestamp fields in priority order)
    "served_pipeline_checkpoints_fresh": ("pipeline-checkpoints", ("generated_at",)),
    "served_import_health_fresh": ("source-import-health", ("checked_at", "generated_at")),
}


def parse_ts(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def artifact_age_minutes(payload, fields, now):
    """Age of the artifact's own timestamp in minutes, or None (= stale)."""
    if not isinstance(payload, dict):
        return None
    for field in fields:
        ts = parse_ts(payload.get(field))
        if ts is not None:
            return (now - ts).total_seconds() / 60.0
    return None


def evaluate(payload, fields, now, max_age=MAX_AGE_MINUTES):
    """Return (ok, age_minutes, error_code). Fail-closed on anything odd."""
    if payload is None:
        return False, None, "unreachable_or_unparseable"
    age = artifact_age_minutes(payload, fields, now)
    if age is None:
        return False, None, "missing_timestamp"
    if age < -5:
        return False, age, "timestamp_in_future"
    if age > max_age:
        return False, age, f"stale_{int(age)}m"
    return True, age, None


def fetch_from_supabase(name: str, supabase_url: str, api_key: str, timeout: int = 30):
    """Fetch an artifact payload from public.ops_artifacts.

    Returns (payload_dict_or_None, latency_ms).
    """
    started = time.monotonic()
    url = f"{supabase_url.rstrip('/')}/rest/v1/ops_artifacts?name=eq.{name}&select=payload,produced_at"
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", api_key)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        latency = int((time.monotonic() - started) * 1000)
        if not rows:
            return None, latency
        row = rows[0]
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return None, latency
        # Attach produced_at so the watch can use it as a fallback timestamp.
        if "produced_at" not in payload and row.get("produced_at"):
            payload = dict(payload, produced_at=row["produced_at"])
        return payload, latency
    except Exception:  # noqa: BLE001 - fail-closed
        return None, int((time.monotonic() - started) * 1000)


def record(check_id, ok, content_ok, http_status, latency_ms, error_code, dry_run):
    if dry_run:
        return
    import sbclient  # noqa: PLC0415 - env-shimmed client (gh_sbclient.py)
    sbclient.rpc("monitoring_record_observation", {
        "p_check_id": check_id, "p_ok": ok, "p_content_ok": content_ok,
        "p_http_status": http_status, "p_latency_ms": latency_ms,
        "p_error_code": error_code, "p_scheduler_owner_id": OWNER,
    })


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-age-minutes", type=float, default=MAX_AGE_MINUTES)
    ap.add_argument("--producer-ok", choices=("true", "false"), default=None,
                    help="also record the CI producer observation")
    ap.add_argument("--dry-run", action="store_true", help="do not write to Supabase")
    args = ap.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    api_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not api_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set; cannot watch artifacts",
              file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    stale = []
    if args.producer_ok is not None:
        ok = args.producer_ok == "true"
        record("health_artifacts_producer", ok, ok, None, None,
               None if ok else "producer_build_failed", args.dry_run)
        print(f"health_artifacts_producer: {'ok' if ok else 'FAILED'}")

    for check_id, (name, fields) in ARTIFACTS.items():
        payload, latency = fetch_from_supabase(name, supabase_url, api_key)
        ok, age, err = evaluate(payload, fields, now, args.max_age_minutes)
        # Record as an HTTP-200 equivalent when Supabase responds (no HTTP status
        # concept for the REST GET; use 200 on success, None on failure).
        http_status = 200 if payload is not None else None
        record(check_id, ok, ok, http_status, latency, err, args.dry_run)
        age_txt = "n/a" if age is None else f"{age:.0f} min"
        print(f"{check_id}: {'ok' if ok else 'STALE'} ({name}, age {age_txt}"
              f"{', ' + err if err else ''})")
        if not ok:
            stale.append(check_id)

    if stale:
        print(f"\nRED: stale health artifacts in Supabase: {', '.join(stale)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
