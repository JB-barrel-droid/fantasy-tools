#!/usr/bin/env python3
"""Surgically annotate the current players.json with CBS ROS native PPG.

JEG-ECR-EXIT (2026-10-05): the full bake (bake_players.py) no longer reads
fp_season_latest_norm / fp_season_projections (ESPN is the primary leg,
sourced from data/inputs/espn_projections.csv). This script still reuses
bake_players._intake_cbsros (the CBS ROS read path is unaffected), so no
existing baked value changes.

This script ONLY ADDS cbsros_* fields, reusing bake_players._intake_cbsros
(the same intake the full bake uses), so no existing baked value changes.
Vintage is recorded in meta.cbsros_snapshot. Idempotent: re-running
replaces the cbsros_* fields with the latest snapshot's values.

Writer-contract note (JEG-423): bake_players.py already writes the same
cbsros_* fields itself on every full bake, so this is a surgical fallback,
not the primary path — run it only when the full bake cannot (e.g. Supabase
unreachable) but the CBS vintage must advance. No workflow or Makefile
calls it; it is manual-only and touches no other field family.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

from bake_players import (  # noqa: E402
    SCORINGS,
    _intake_cbsros,
    _latest_cbsros_snapshot,
)
from canonical_players import load_registry  # noqa: E402
from games_remaining import PPG_DECIMALS  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "players.json"
SNAPSHOT_DIR = ROOT / "data" / "fixtures" / "snapshots"

CBSROS_NOTE = ("cbsros_ppg = pure CBS rest-of-season per-game "
               "projection read (per_game_standard / per_game_half_ppr / "
               "per_game_ppr from the CBS ROS snapshot = ROS totals / gp). "
               "CBS publishes nonppr totals only; half_ppr/ppr add 0.5/1.0 "
               "per reception. The curve re-prices live from cbsros_ppg "
               "through the shared two-tier value-above-waivers math "
               "(source's own pool and pies, never ESPN's). K/DST have no "
               "CBS ROS projections.")


def main():
    registry = load_registry()
    snap_path = _latest_cbsros_snapshot()
    cbsros_med, vintage = _intake_cbsros(snap_path, registry)
    if not cbsros_med:
        raise SystemExit("FAIL-CLOSED: cbsros intake priced 0 players.")

    payload = json.loads(FIXTURE.read_text())
    players = payload["players"]
    n = 0
    for p in players:
        key = p.get("player_key")
        c = cbsros_med.get(key, {})
        complete = (p.get("pos") in ("QB", "RB", "WR", "TE")
                    and all(s in c for s in SCORINGS))
        covered = sorted(s for s in SCORINGS if s in c)
        p["cbsros_complete"] = bool(complete)
        p["cbsros_comp_count"] = len(covered)
        p["cbsros_covered"] = covered
        if complete:
            p["cbsros_ppg"] = {s: round(c[s], PPG_DECIMALS) for s in SCORINGS}
            n += 1
        else:
            p.pop("cbsros_ppg", None)

    meta = payload["meta"]
    meta["cbsros_snapshot"] = str(vintage)
    meta["n_cbsros_complete"] = n
    meta["cbsros_note"] = CBSROS_NOTE

    # Snapshot the previous fixture before overwriting (same as the bake).
    prev_asof = meta.get("as_of", "unknown")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_out = SNAPSHOT_DIR / f"players_{prev_asof}.json"
    if not snap_out.exists():
        snap_out.write_text(json.dumps(
            json.loads(FIXTURE.read_text()), indent=1))
        print(f"snapshotted previous fixture -> {snap_out.name}")

    FIXTURE.write_text(json.dumps(payload, indent=1))
    print(f"annotated {FIXTURE} ({len(players)} players, "
          f"{n} cbsros_complete, vintage {vintage})")


if __name__ == "__main__":
    main()
