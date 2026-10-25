#!/usr/bin/env python3
"""One-time backfill of source_projection_captures from data/history/week-N.json (JEG-944).

What is recoverable, and only this: each week-history file holds, per source
(espn, razzball, cbsros), the ROS per-game values the chart build used
(`ppg.<player_key> = [standard, half_ppr, ppr]`) and the time they were captured.
They become horizon 'ros' rows (ppg only; no totals, no games) with the file's
captured_at as capture_at and N as source_week. Nothing else about earlier weeks
exists in the repo (no CBS or ESPN per-week projections, no Razzball week pages).

Caveats stored in `basis`: the values are the build's per-game numbers, not the raw
published pages; ESPN weeks 2-4 share one captured_at (2026-10-08), a rebuild stamp
rather than the true capture time of each week.

Default is a dry run that prints what would be written. --write appends (a key
already stored is left alone), after dropping player_keys public.players does not hold.

Usage: python3 pipelines/backfill_projection_captures.py [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import projection_capture as pc  # noqa: E402

HISTORY = ROOT / "data" / "history"
SOURCE_OF = {"espn": "espn", "razzball": "razzball", "cbsros": "cbs"}
FORMAT_AT = (("standard", 0), ("half_ppr", 1), ("full_ppr", 2))


def rows_from_history(path: Path, batch_id: str) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    week, season = int(d["week"]), int(d["season"])
    out = []
    for hist_key, source in SOURCE_OF.items():
        sec = (d.get("sources") or {}).get(hist_key) or {}
        ppg = sec.get("ppg") or {}
        if not ppg or not sec.get("captured_at"):
            continue
        for pk, triple in ppg.items():
            for fmt, i in FORMAT_AT:
                if triple is None or triple[i] is None:
                    continue
                out.append(pc.capture_row(
                    source=source, season=season, source_week=week,
                    capture_at=sec["captured_at"], phase="backfill", horizon="ros", target_week=0,
                    player_key=int(pk), scoring_format=fmt, ppg=triple[i], batch_id=batch_id,
                    basis=f"backfill from data/history/week-{week}.json {hist_key}_ppg "
                          "(chart-build per-game ROS value; no total or games)"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    batch = pc.new_batch()
    rows = []
    for path in sorted(HISTORY.glob("week-*.json")):
        rows += rows_from_history(path, batch)
    summary: dict = {}
    for r in rows:
        k = f"{r['source']} week {r['source_week']}"
        summary[k] = summary.get(k, 0) + 1
    print(json.dumps({"planned": len(rows), "by_source_week": summary}, indent=1))
    if not a.write:
        print("dry run; pass --write to append")
        return 0
    try:
        import sbclient  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(ROOT / "pipelines"))
        import gh_sbclient as sbclient  # noqa: PLC0415
    known = {p["player_key"] for p in sbclient.get_all("players", "?select=id,player_key")}
    keep = [r for r in rows if r["player_key"] in known]
    print(f"dropping {len(rows) - len(keep)} rows whose player_key is not in public.players")
    print(f"wrote {pc.write_capture(sbclient, keep)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
