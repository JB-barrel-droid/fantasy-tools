#!/usr/bin/env python3
"""JEG-414 (ARCH-013): independent freshness watch for the served health artifacts.

The served monitor JSON (modules/pipeline-checkpoints.json and
modules/source-import-health.json) has been produced only by the Muse
30-minute cron. If that cron stops, the files keep their last contents and
look live. This watch runs from GitHub Actions (health-artifacts.yml),
independent of Muse:

  * fetches each served artifact and measures the age of its own timestamp
    (generated_at / checked_at) -- never HTTP Last-Modified or fetch time;
  * records one observation per artifact into Supabase
    monitoring.check_observations via public.monitoring_record_observation
    (the pg_cron evaluator marks the check 'missed' if this workflow itself
    stops reporting);
  * compares the CI-built shadow artifacts against the served copies and
    prints a parity table for the cutover decision;
  * exits 1 when any served artifact is older than MAX_AGE_MINUTES (red).

Fail-closed: an unreachable artifact, unparseable JSON or a missing
timestamp is stale, never fresh.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://jb-barrel-droid.github.io/fantasy-tools/modules/"
MAX_AGE_MINUTES = 60  # twice the 30-minute heartbeat (BH-8)
OWNER = "health-artifacts.yml"

ARTIFACTS = {
    # check_id: (served file, timestamp fields in priority order)
    "served_pipeline_checkpoints_fresh": ("pipeline-checkpoints.json", ("generated_at",)),
    "served_import_health_fresh": ("source-import-health.json", ("checked_at", "generated_at")),
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


def fetch_json(url, timeout=30):
    started = time.monotonic()
    try:
        req = urllib.request.Request(f"{url}?cb={int(time.time())}",
                                     headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
        payload = json.loads(body)
    except Exception:  # noqa: BLE001 - fail-closed, reported as stale
        return None, None, int((time.monotonic() - started) * 1000)
    return payload, status, int((time.monotonic() - started) * 1000)


def record(check_id, ok, content_ok, http_status, latency_ms, error_code, dry_run):
    if dry_run:
        return
    import sbclient  # noqa: PLC0415 - env-shimmed client (gh_sbclient.py)
    sbclient.rpc("monitoring_record_observation", {
        "p_check_id": check_id, "p_ok": ok, "p_content_ok": content_ok,
        "p_http_status": http_status, "p_latency_ms": latency_ms,
        "p_error_code": error_code, "p_scheduler_owner_id": OWNER,
    })


def parity_rows(shadow_dir):
    """Checkpoint-status parity between CI shadow and served copies."""
    rows = []
    shadow = shadow_dir / "pipeline-checkpoints.json"
    if not shadow.exists():
        return rows
    ci = json.loads(shadow.read_text(encoding="utf-8"))
    served, _, _ = fetch_json(BASE_URL + "pipeline-checkpoints.json")
    for src, entry in sorted((ci.get("sources") or {}).items()):
        cps = (entry or {}).get("checkpoints") or {}
        served_cps = (((served or {}).get("sources") or {}).get(src) or {}).get("checkpoints") or {}
        for key, cp in sorted(cps.items()):
            a = (served_cps.get(key) or {}).get("status")
            b = (cp or {}).get("status")
            if a != b:
                rows.append((src, key, a, b))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--max-age-minutes", type=float, default=MAX_AGE_MINUTES)
    ap.add_argument("--shadow-dir", type=Path, default=ROOT / "output")
    ap.add_argument("--producer-ok", choices=("true", "false"), default=None,
                    help="also record the CI producer observation")
    ap.add_argument("--dry-run", action="store_true", help="do not write to Supabase")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    stale = []
    if args.producer_ok is not None:
        ok = args.producer_ok == "true"
        record("health_artifacts_producer", ok, ok, None, None,
               None if ok else "producer_build_failed", args.dry_run)
        print(f"health_artifacts_producer: {'ok' if ok else 'FAILED'}")
    for check_id, (name, fields) in ARTIFACTS.items():
        payload, status, latency = fetch_json(args.base_url + name)
        ok, age, err = evaluate(payload, fields, now, args.max_age_minutes)
        record(check_id, ok, ok, status, latency, err, args.dry_run)
        age_txt = "n/a" if age is None else f"{age:.0f} min"
        print(f"{check_id}: {'ok' if ok else 'STALE'} ({name}, age {age_txt}"
              f"{', ' + err if err else ''})")
        if not ok:
            stale.append(check_id)

    rows = parity_rows(args.shadow_dir)
    print(f"\nCI-shadow vs served checkpoint parity: {len(rows)} status differences")
    for src, key, served, ci in rows:
        print(f"  {src}/{key}: served={served} ci={ci}")
    if stale:
        print(f"\nRED: stale served health artifacts: {', '.join(stale)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
