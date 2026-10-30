#!/usr/bin/env python3
"""Capture CBS and Razzball projections into source_projection_captures, nothing else (JEG-944).

The Sunday pre-kickoff copy (Jeremy 2026-10-23). Reads the snapshots the pull scripts wrote
(pull_cbs_ros_projections.py -> snapshot.json + weekly_snapshot.json,
pull_razzball_ros.py -> snapshot.json) and runs the same capture step the savers run,
without upserting cbs_ros_projections or razzball_projections, so it cannot move a published
value or start a rebuild. Phase is derived from the clock (Sunday -> sunday); the first
capture of a phase in a content week wins. A fault is printed as a ::error annotation and the
exit code is 1, since this run does nothing else; check_projection_captures.py is the gate.

A dry run (JEG-1377) builds both sources' capture rows exactly as a write would, writes
nothing, and exits 1 when a horizon the source must hold comes in under its row floor
(pc.MIN_ROWS), so a dispatch on a branch proves the Sunday job end to end.

Usage: python3 pipelines/capture_projections_only.py --cbs DIR --razzball DIR [--dry-run]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import projection_capture as pc  # noqa: E402
import save_cbsros_references as sc  # noqa: E402
import save_razzball_references as sr  # noqa: E402


def plan(cbs_snap: Path, clean: list[dict], cbs_vintage, rz_vintage, resolve, *, now=None) -> list[str]:
    """Build both sources' capture rows as a write would and check each required horizon
    against its floor. Writes nothing. -> problems (empty when every horizon clears)."""
    now = now or datetime.now(timezone.utc)
    common = dict(season=2026, source_week=0, capture_at=now.isoformat(),
                  phase=pc.capture_phase(now), batch_id="dry-run")
    snap = json.loads(cbs_snap.read_text(encoding="utf-8"))
    weekly_path = cbs_snap.with_name("weekly_snapshot.json")
    weekly = json.loads(weekly_path.read_text(encoding="utf-8")) if weekly_path.exists() else None
    cbs_rows, rep = pc.cbs_capture_rows(snap.get("rows", []), weekly, resolve, vintage=cbs_vintage, **common)
    rz_rows = pc.razzball_capture_rows(clean, vintage=rz_vintage, **common)
    print(f"[dry-run] phase {common['phase']}; cbs plan {json.dumps(rep, default=str)}")
    problems = []
    for source, rows in (("cbs", cbs_rows), ("razzball", rz_rows)):
        for h in pc.REQUIRED_HORIZONS[source]:
            n, floor = sum(1 for r in rows if r["horizon"] == h), pc.MIN_ROWS[(source, h)]
            print(f"[dry-run] {source} {h}: {n} rows planned (floor {floor})")
            if n < floor:
                problems.append(f"{source} {h}: {n} rows planned, below the floor of {floor}")
    return problems


def _cbs_resolver():
    registry = sc.build_registry(sc.fetch_players())
    return lambda n, p, norm: sc.resolve_name(str(n or "").strip(), (p or "").upper() or None, registry, norm)[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cbs", type=Path, required=True, help="dir holding snapshot.json and weekly_snapshot.json")
    ap.add_argument("--razzball", type=Path, required=True, help="dir holding snapshot.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    cbs_snap, rz_snap = a.cbs / "snapshot.json", a.razzball / "snapshot.json"
    clean, review, rz_vintage = sr.build_razzball_rows(rz_snap)
    cbs_vintage = json.loads(cbs_snap.read_text(encoding="utf-8")).get("vintage_date")
    print(f"razzball {rz_vintage}: {len(clean)} resolved rows ({len(review)} review); cbs {cbs_vintage}")
    if a.dry_run:
        problems = plan(cbs_snap, clean, cbs_vintage, rz_vintage, _cbs_resolver())
        for p in problems:
            print(f"::error title=projection capture dry run::{p}")
        print("[dry-run] nothing written")
        return 1 if problems else 0
    buf = io.StringIO()
    with redirect_stdout(buf):
        sc.save_captures(cbs_snap, cbs_vintage)
        sr.save_captures(clean, rz_vintage)
    out = buf.getvalue()
    print(out, end="")
    return 1 if "::error" in out else 0


if __name__ == "__main__":
    sys.exit(main())
