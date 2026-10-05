#!/usr/bin/env python3
"""Export a CBS ROS snapshot.json from Supabase (system of record).

JEG-392 / ARCH-013: bake_players.py reads CBS ROS per-game rates from
data/raw/sources/cbsros/<date>/snapshot.json, which only exists on the Mac
that ran the scrape. The same rows are saved to public.cbs_ros_projections
by save_cbsros_references.py, so a non-Mac producer (GitHub Actions) can
rebuild the identical bake input from Supabase instead of re-scraping.

Output rows carry exactly the fields _intake_cbsros() consumes:
player_name (the saved player_norm), pos (canonical registry position for
the saved player_key), per_game_standard / per_game_half_ppr / per_game_ppr.
Fail-closed: no rows for the requested date, or a saved player_key missing
from the canonical registry, exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

from canonical_players import load_registry  # noqa: E402

OUT_DIR = ROOT / "data" / "raw" / "sources" / "cbsros"
COLS = ("player_key", "player_norm", "per_game_standard", "per_game_half_ppr",
        "per_game_ppr", "cbs_snapshot_date")


def latest_date(sbclient) -> str:
    rows = sbclient.get_all(
        "cbs_ros_projections",
        "?select=cbs_snapshot_date&order=cbs_snapshot_date.desc&limit=1")
    if not rows:
        raise SystemExit("FAIL-CLOSED: cbs_ros_projections is empty.")
    return str(rows[0]["cbs_snapshot_date"])


def build_snapshot(rows, registry, vintage):
    out, missing = [], []
    for r in rows:
        key = r.get("player_key")
        entry = registry.by_key.get(int(key)) if key is not None else None
        if entry is None:
            missing.append(key)
            continue
        out.append({
            "player_name": r["player_norm"],
            "player_norm": r["player_norm"],
            "pos": entry["position"],
            "per_game_standard": r["per_game_standard"],
            "per_game_half_ppr": r["per_game_half_ppr"],
            "per_game_ppr": r["per_game_ppr"],
        })
    if missing:
        raise SystemExit(f"FAIL-CLOSED: {len(missing)} saved player_keys are "
                         f"not in the canonical registry: {missing[:5]}")
    if not out:
        raise SystemExit(f"FAIL-CLOSED: no CBS ROS rows for {vintage}.")
    return {"vintage_date": vintage, "row_count": len(out),
            "exported_from": "supabase:cbs_ros_projections", "rows": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="cbs_snapshot_date; default: latest saved")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    import sbclient  # noqa: PLC0415 - env-shimmed client (gh_sbclient.py)
    vintage = args.date or latest_date(sbclient)
    rows = sbclient.get_all(
        "cbs_ros_projections",
        f"?select={','.join(COLS)}&cbs_snapshot_date=eq.{vintage}")
    snap = build_snapshot(rows, load_registry(), vintage)
    path = args.out_dir / vintage / "snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path} ({snap['row_count']} rows, vintage {vintage})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
