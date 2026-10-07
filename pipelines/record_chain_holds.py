#!/usr/bin/env python3
"""Record the rebuild chain's held sources as two monitored checks.

Per-source promotion (decision per-source-promotion-001, 2026-10-07): a
source whose review verdict is 'hold' no longer fails the chain. The other
sources publish and the held source keeps its last promoted section. That
must stay loud, so every chain run records:

  rebuild_chain_source_held        (severity warn -> yellow/amber)
      not ok whenever ANY source was held this run.
  rebuild_chain_source_held_stale  (severity page -> red)
      not ok when a held source's kept section is two or more content weeks
      behind (or its week is unknown): it has been held for more than a week.

The evaluator only reads `ok`, so amber vs red comes from the two checks'
severities (monitoring_summary maps error+warn -> yellow, error+page -> red).

Input is output/comparison-chain-status.json written by
rebuild_comparison_chain.py. When the chain step did not run (`--chain-outcome`
skipped/cancelled, e.g. the import-health gate was red) nothing is recorded:
the status file on disk is then an older run's and says nothing about now.
An unreadable status after a run is recorded as not ok on both checks.

Never fails the job (same contract as record_monitor_check.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "output" / "comparison-chain-status.json"
CHECK_HELD = "rebuild_chain_source_held"
CHECK_HELD_STALE = "rebuild_chain_source_held_stale"
RAN_OUTCOMES = ("success", "failure")


def _payload(check_id, ok, error_code, owner):
    return {
        "p_check_id": check_id,
        "p_ok": ok,
        "p_content_ok": ok,
        "p_error_code": None if ok else error_code,
        "p_scheduler_owner_id": owner,
    }


def build_payloads(status, owner, chain_outcome):
    """RPC payloads for one chain run, or [] when nothing should be recorded."""
    if chain_outcome not in RAN_OUTCOMES:
        return []
    if not isinstance(status, dict) or not isinstance(status.get("held"), list):
        return [_payload(CHECK_HELD, False, "CHAIN_STATUS_UNREADABLE", owner),
                _payload(CHECK_HELD_STALE, False, "CHAIN_STATUS_UNREADABLE", owner)]
    held = sorted(status["held"])
    detail = status.get("held_detail") or {}
    stale = sorted(s for s in held
                   if (detail.get(s) or {}).get("hold_severity") != "amber")
    return [
        _payload(CHECK_HELD, not held, "SOURCE_HELD:" + ",".join(held), owner),
        _payload(CHECK_HELD_STALE, not stale, "SOURCE_HELD_2W:" + ",".join(stale), owner),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--owner", required=True, help="workflow file, e.g. rebuild-chain.yml")
    ap.add_argument("--chain-outcome", required=True, help="steps.chain.outcome")
    ap.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        status = json.loads(args.status.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = None
    payloads = build_payloads(status, args.owner, args.chain_outcome)
    if not payloads:
        print(f"chain outcome {args.chain_outcome!r}: hold checks not recorded")
        return 0
    for payload in payloads:
        line = f"{payload['p_check_id']}: ok={payload['p_ok']} {payload['p_error_code'] or ''}"
        if args.dry_run:
            print("would record " + line)
            continue
        try:
            import gh_sbclient as sbclient  # noqa: PLC0415 - env-based client
            sbclient.rpc("monitoring_record_observation", payload)
        except Exception as exc:  # noqa: BLE001 - never fail the job over the recorder
            print(f"::warning title=monitor-record::could not record {payload['p_check_id']}: {exc}")
            continue
        print("recorded " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
