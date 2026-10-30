#!/usr/bin/env python3
"""JEG-414 (ARCH-013): independent freshness watch for the served health artifacts.

The served monitor JSON (modules/pipeline-checkpoints.json and
modules/source-import-health.json) has been produced only by the Muse
30-minute cron (now this workflow, every 6 hours). If it stops, the files keep their last contents and
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
  * exits 1 when any served artifact is older than MAX_AGE_MINUTES (red), and
    2 or 3 when this run's publication did not arrive or cannot be verified
    (JEG-1239, below).

--await-published DIR (2026-10-08): when this run has just pushed new
artifacts and dispatched the Pages deploy, the served copies are still the
previous deploy's for the next ~10 minutes. Measuring them at once judged the
last run's output, not this one's: three runs in a row went red (37638759289,
37645910631, 37779712658) while their own fresh artifacts were mid-deploy.
With the flag the watch first polls until each served artifact carries at
least the timestamp of the copy in DIR (what this run published), up to
--await-timeout-minutes, then judges the served copy as usual. A deploy that
never lands still ends red, because the served copy is then really stale.

Publication arrival (JEG-1239, 2026-10-29): "the served copy is then really
stale" only held while the limit was 60 minutes. At 720 minutes a deploy that
never lands left a valid previous copy (observed 386 and 109 minutes old)
judged fresh, and the run went green as if this run's artifacts had arrived.
Arrival is now its own outcome per artifact, separate from content freshness
and from source coverage:

  * arrived      -- the served copy carries at least the published timestamp;
  * not_arrived  -- the served copy is readable but older than what this run
                    published (a publication mismatch, never a source-feed
                    outage);
  * unverified   -- the evidence is inaccessible (fetch denied, e.g. HTTP 403,
                    or failed) or a timestamp is missing or malformed, so
                    arrival is unknown: not declared failed or recovered;
  * not_awaited  -- no --await-published, nothing was expected.

The wait window is unchanged (--await-timeout-minutes, default 25). Each
outcome describes the copy judged after the wait (the fetch freshness also
reads), not the best copy the wait saw: a copy that lands late still arrives,
and one seen during the wait but replaced by the previous deploy or denied at
judgment is not_arrived or unverified. The wait's last observation is kept as
`observed_during_wait`. The outcome is printed as one `publication_arrival: {json}` line and,
with --result-json PATH, written to a file. Exit codes: 0 fresh and arrived,
1 a served artifact is stale (unchanged, takes precedence), 2 this run's
publication did not arrive, 3 its arrival could not be verified.
health-artifacts.yml treats 3 as a warning and keeps the run green (Jeremy,
2026-10-30, JEG-1239: "A"); 1 and 2 still fail it.

Fail-closed: an unreachable artifact, unparseable JSON or a missing
timestamp is stale, never fresh.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp  # noqa: E402
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://jb-barrel-droid.github.io/fantasy-tools/modules/"
MAX_AGE_MINUTES = 720  # twice the 6-hour heartbeat (BH-8); pg_cron health-artifacts-live, 2026-10-08
OWNER = "health-artifacts.yml"

EXIT_OK = 0
EXIT_STALE = 1
EXIT_NOT_ARRIVED = 2
EXIT_ARRIVAL_UNVERIFIED = 3

ARRIVED = "arrived"
NOT_ARRIVED = "not_arrived"
UNVERIFIED = "unverified"
NOT_AWAITED = "not_awaited"

ARTIFACTS = {
    # check_id: (served file, timestamp fields in priority order)
    "served_pipeline_checkpoints_fresh": ("pipeline-checkpoints.json", ("generated_at",)),
    "served_import_health_fresh": ("source-import-health.json", ("checked_at", "generated_at")),
}


def parse_ts(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = parse_iso_timestamp(value.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def artifact_ts(payload, fields):
    """The artifact's own timestamp (first field present), or None."""
    if not isinstance(payload, dict):
        return None
    for field in fields:
        ts = parse_ts(payload.get(field))
        if ts is not None:
            return ts
    return None


def artifact_age_minutes(payload, fields, now):
    """Age of the artifact's own timestamp in minutes, or None (= stale)."""
    ts = artifact_ts(payload, fields)
    return None if ts is None else (now - ts).total_seconds() / 60.0


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
    except urllib.error.HTTPError as exc:  # keep the status: a 403 is denial, not absence
        return None, exc.code, int((time.monotonic() - started) * 1000)
    except Exception:  # noqa: BLE001 - fail-closed, reported as stale
        return None, None, int((time.monotonic() - started) * 1000)
    return payload, status, int((time.monotonic() - started) * 1000)


def _iso(ts):
    return None if ts is None else ts.isoformat()


def published_expectations(published_dir):
    """{file name: expected timestamp or None} for the copies this run published."""
    expected = {}
    for name, fields in ARTIFACTS.values():
        try:
            ts = artifact_ts(json.loads((Path(published_dir) / name).read_text(encoding="utf-8")), fields)
        except (OSError, ValueError):
            ts = None
        expected[name] = ts
    return expected


def judge_arrival(expected, fetched, fields):
    """Did the served copy reach this run's published artifact?

    expected: the published timestamp (None when the published copy has none).
    fetched: fetch_json's (payload, http_status, latency_ms).
    Only arrival is judged here; content freshness is evaluate()'s job, so a
    valid but older copy is not_arrived however fresh its content still is.
    """
    payload, status, _ = fetched
    result = {"outcome": UNVERIFIED, "reason": None, "expected_at": _iso(expected),
              "served_at": None, "http_status": status}
    if expected is None:
        result["reason"] = "published_timestamp_missing"
        return result
    if payload is None:
        result["reason"] = "fetch_denied" if status in (401, 403) else "fetch_failed"
        return result
    served = artifact_ts(payload, fields)
    result["served_at"] = _iso(served)
    if served is None:
        result["reason"] = "served_timestamp_missing"
    elif served >= expected:
        result["outcome"] = ARRIVED
    else:
        result.update(outcome=NOT_ARRIVED, reason="served_copy_older_than_published")
    return result


def await_arrival(base_url, published_dir, timeout_s, interval_s=60,
                  fetch=None, sleep=time.sleep, clock=time.monotonic, log=print):
    """Poll until every served artifact is at least as new as the copy this run
    published into published_dir, up to timeout_s. Returns {file name: result}
    (judge_arrival's dict) from the last poll. Never raises."""
    fetch = fetch or fetch_json
    fields_by_name = dict(ARTIFACTS.values())
    results = {}
    pending = {}
    for name, want in published_expectations(published_dir).items():
        if want is None:
            results[name] = judge_arrival(None, (None, None, 0), fields_by_name[name])
            log(f"::warning title=publication arrival::{name} published by this run has no timestamp; "
                f"its arrival cannot be verified")
        else:
            pending[name] = want
    deadline = clock() + timeout_s
    while pending:
        for name, want in list(pending.items()):
            result = judge_arrival(want, fetch(base_url + name), fields_by_name[name])
            results[name] = result
            if result["outcome"] == ARRIVED:
                log(f"served {name} now carries this run's artifact ({want.isoformat()})")
                del pending[name]
        if not pending or clock() >= deadline:
            break
        sleep(interval_s)
    for name in pending:
        r = results[name]
        log(f"::warning title=health watch::served {name} did not reach this run's artifact "
            f"within {timeout_s / 60:.0f} min ({r['outcome']}: {r['reason']}); it is not counted as "
            f"arrived. Content freshness is judged separately")
    return results


def await_published(base_url, published_dir, timeout_s, interval_s=60,
                    fetch=None, sleep=time.sleep, clock=time.monotonic, log=print):
    """Names of the artifacts that did not arrive within the window (empty when
    the deploy landed). Kept for callers of the pre-JEG-1239 interface."""
    results = await_arrival(base_url, published_dir, timeout_s, interval_s,
                            fetch=fetch, sleep=sleep, clock=clock, log=log)
    return sorted(n for n, r in results.items() if r["outcome"] != ARRIVED)


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


def _utcnow():
    return datetime.now(timezone.utc)


def exit_code(stale, arrival):
    """Stale first (unchanged contract), then a missed publication, then unknown arrival."""
    if stale:
        return EXIT_STALE
    outcomes = {r["outcome"] for r in arrival.values()}
    if NOT_ARRIVED in outcomes:
        return EXIT_NOT_ARRIVED
    if UNVERIFIED in outcomes:
        return EXIT_ARRIVAL_UNVERIFIED
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--max-age-minutes", type=float, default=MAX_AGE_MINUTES)
    ap.add_argument("--shadow-dir", type=Path, default=ROOT / "output")
    ap.add_argument("--producer-ok", choices=("true", "false"), default=None,
                    help="also record the CI producer observation")
    ap.add_argument("--dry-run", action="store_true", help="do not write to Supabase")
    ap.add_argument("--await-published", type=Path, default=None, metavar="DIR",
                    help="first wait for the served copies to reach the artifacts this run published in DIR")
    ap.add_argument("--await-timeout-minutes", type=float, default=25.0)
    ap.add_argument("--await-interval-seconds", type=float, default=60.0)
    ap.add_argument("--result-json", type=Path, default=None, metavar="PATH",
                    help="also write the freshness and publication-arrival outcome as JSON")
    args = ap.parse_args(argv)

    awaited = {}
    if args.await_published is not None:
        awaited = await_arrival(args.base_url, args.await_published, args.await_timeout_minutes * 60,
                                args.await_interval_seconds)

    now = _utcnow()  # after the wait: age is judged when measured
    stale = []
    freshness = {}
    arrival = {}
    if args.producer_ok is not None:
        ok = args.producer_ok == "true"
        record("health_artifacts_producer", ok, ok, None, None,
               None if ok else "producer_build_failed", args.dry_run)
        print(f"health_artifacts_producer: {'ok' if ok else 'FAILED'}")
    for check_id, (name, fields) in ARTIFACTS.items():
        fetched = fetch_json(args.base_url + name)
        payload, status, latency = fetched
        ok, age, err = evaluate(payload, fields, now, args.max_age_minutes)
        record(check_id, ok, ok, status, latency, err, args.dry_run)
        age_txt = "n/a" if age is None else f"{age:.0f} min"
        print(f"{check_id}: {'ok' if ok else 'STALE'} ({name}, age {age_txt}"
              f"{', ' + err if err else ''})")
        if not ok:
            stale.append(check_id)
        freshness[check_id] = {"file": name, "ok": ok, "age_minutes": age, "error_code": err,
                               "http_status": status}
        if args.await_published is None:
            arrival[check_id] = {"file": name, "outcome": NOT_AWAITED}
            continue
        observed = awaited.get(name) or judge_arrival(None, (None, None, 0), fields)
        current = observed
        if observed["expected_at"] is not None:
            # The outcome is the currently judged copy, the same fetch freshness
            # reads: a late deploy still arrives, a copy that went back to the
            # previous deploy is not_arrived, and a denied fetch is unverified,
            # whatever the wait saw earlier. The wait's last observation is
            # kept beside it as evidence, never as the outcome.
            current = judge_arrival(parse_ts(observed["expected_at"]), fetched, fields)
        arrival[check_id] = {"file": name, **current, "observed_during_wait": {
            k: observed[k] for k in ("outcome", "reason", "served_at", "http_status")}}

    print("publication_arrival: " + json.dumps(
        {"awaited": args.await_published is not None, "artifacts": arrival}, sort_keys=True))
    missed = [c for c, r in arrival.items() if r["outcome"] == NOT_ARRIVED]
    unknown = [c for c, r in arrival.items() if r["outcome"] == UNVERIFIED]

    rows = parity_rows(args.shadow_dir)
    print(f"\nCI-shadow vs served checkpoint parity: {len(rows)} status differences")
    for src, key, served, ci in rows:
        print(f"  {src}/{key}: served={served} ci={ci}")
    rc = exit_code(stale, arrival)
    if args.result_json is not None:
        args.result_json.write_text(json.dumps(
            {"exit_code": rc, "freshness": freshness, "publication_arrival": arrival,
             "awaited": args.await_published is not None}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    if stale:
        print(f"\nRED: stale served health artifacts: {', '.join(stale)}", file=sys.stderr)
    if missed:
        print(f"\nRED: this run's published health artifacts did not arrive on the served site: "
              f"{', '.join(missed)} (served copy older than published: a publication mismatch, "
              f"not a source-feed outage)", file=sys.stderr)
    if unknown:
        print(f"\nUNVERIFIED: arrival of this run's health artifacts is unknown: {', '.join(unknown)} "
              f"(evidence inaccessible or timestamp missing; not declared failed or recovered)",
              file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
