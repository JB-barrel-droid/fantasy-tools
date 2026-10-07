#!/usr/bin/env python3
"""Record one monitoring observation for a scheduled workflow, success or failure.

Every workflow that pg_cron dispatches (or that has its own schedule) ends with
an `if: always()` step that calls this, so a red run is recorded as red and a
run that never happens is flagged `missed` by the evaluator
(monitoring.run_evaluator_cycle). Check ids and owners are declared in
config/monitoring_coverage.json and enforced by tests/test_monitoring_coverage.py.

    python3 pipelines/record_monitor_check.py --check-id rebuild_chain \
        --owner rebuild-chain.yml --outcome "${{ job.status }}"

`outcome` is the GitHub job status: success -> ok; failure -> not ok;
cancelled / skipped -> nothing recorded (a cancelled run says nothing about
health). The step never fails the job: if the record cannot be written the
evaluator reports the check `missed`, which is the correct alarm.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUTCOMES = {"success": True, "failure": False}


def build_payload(check_id, owner, outcome):
    """RPC payload for an outcome, or None when nothing should be recorded."""
    if outcome not in OUTCOMES:
        return None
    ok = OUTCOMES[outcome]
    return {
        "p_check_id": check_id,
        "p_ok": ok,
        "p_content_ok": ok,
        "p_error_code": None if ok else "WORKFLOW_FAILED",
        "p_scheduler_owner_id": owner,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-id", required=True)
    ap.add_argument("--owner", required=True, help="workflow file, e.g. rebuild-chain.yml")
    ap.add_argument("--outcome", required=True, help="GitHub job.status")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    payload = build_payload(args.check_id, args.owner, args.outcome)
    if payload is None:
        print(f"{args.check_id}: outcome={args.outcome!r}, nothing recorded")
        return 0
    if args.dry_run:
        print(f"{args.check_id}: would record ok={payload['p_ok']}")
        return 0
    try:
        import gh_sbclient as sbclient  # noqa: PLC0415 - env-based client
        sbclient.rpc("monitoring_record_observation", payload)
    except Exception as exc:  # noqa: BLE001 - never fail the job over the recorder
        print(f"::warning title=monitor-record::could not record {args.check_id}: {exc}")
        return 0
    print(f"recorded {args.check_id} ok={payload['p_ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
