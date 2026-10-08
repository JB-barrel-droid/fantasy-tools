#!/usr/bin/env python3
"""Surgically refresh players.json ESPN fields from a fresh ESPN CSV.

Pipeline stage: ESPN CSV -> players.json (ESPN fields only). Used when the
full bake_players.py cannot run (e.g. Supabase ECR tables unreachable) but
the ESPN vintage must advance. Updates ONLY ESPN-derived fields; every
ECR/blend/PM/RZ field is left byte-identical.

ESPN fields refreshed (same math as bake_players.py):
- espn_complete, espn_comp_count, espn_covered
- espn_ros / espn_ppg (pure ESPN, per scoring)
- espn_filled_ros / espn_filled_ppg (ESPN where priced; for incomplete
  players the pre-existing ECR-filled values are preserved, since fresh
  ECR is unavailable)
- delta_espn_ecr, delta_espn_ecr_ppg, delta_espn_ecr_ppg_demeaned,
  espn_adj_ppg (recomputed with the same shade math)
- meta.espn_snapshot, meta.n_espn_complete

Fails closed if the CSV vintage is not newer than the current snapshot,
or if the CSV schema is unexpected.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
from scoring import fantasy_points  # noqa: E402
from games_remaining import PPG_DECIMALS  # noqa: E402

FIXTURE_PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
DEFAULT_CSV = REPO / "data" / "inputs" / "espn_projections.csv"

SCORINGS = ("standard", "half_ppr", "ppr")
# CSV component -> COMPS namespace used by fantasy_points.
COMP_MAP = {
    "r_pass_yds": "passing_yards",
    "r_pass_tds": "passing_tds",
    "r_rush_yds": "rushing_yards",
    "r_rush_tds": "rushing_tds",
    "r_receptions": "receptions",
    "r_rec_yds": "receiving_yards",
    "r_rec_tds": "receiving_tds",
}
NEED = {
    "QB": ["passing_yards", "passing_tds"],
    "RB": ["rushing_yards", "receiving_yards"],
    "WR": ["receiving_yards"],
    "TE": ["receiving_yards"],
}


def parse_weeks(weeks_covered: str) -> int:
    # "4-18" -> 15 games remaining.
    a, b = weeks_covered.split("-")
    return int(b) - int(a) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--players", type=Path, default=FIXTURE_PLAYERS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    players_doc = json.loads(args.players.read_text(encoding="utf-8"))
    players = players_doc["players"]
    meta = players_doc["meta"]
    old_vintage = meta.get("espn_snapshot", "")

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    vintages = {r["espn_snapshot_date"] for r in rows}
    if len(vintages) != 1:
        raise SystemExit(f"CSV has mixed vintages: {sorted(vintages)}")
    vintage = vintages.pop()
    if vintage <= old_vintage:
        raise SystemExit(
            f"CSV vintage {vintage} not newer than players.json {old_vintage}; refusing.")
    print(f"CSV vintage {vintage} (old {old_vintage}); {len(rows)} rows")

    # player_norm -> {comp: value, games_remaining}
    espn = {}
    for r in rows:
        if r.get("has_espn_projection") != "True":
            continue
        comps = {}
        for csv_c, comp in COMP_MAP.items():
            try:
                comps[comp] = float(r[csv_c])
            except (ValueError, TypeError):
                pass
        espn[r["player_norm"]] = {
            "comps": comps,
            "gr": parse_weeks(r["weeks_covered"]),
            "pos": r["pos"],
        }

    by_key = {p["player_key"]: p for p in players}
    # norm -> player (match on name norm)
    def norm(name: str) -> str:
        return " ".join(name.lower().split())
    by_norm = {norm(p["name"]): p for p in players}

    n_updated = 0
    n_complete = 0
    for enorm, edata in espn.items():
        p = by_norm.get(enorm)
        if p is None:
            continue
        pos = p["pos"]
        comps = edata["comps"]
        gr = edata["gr"]
        covered = sorted(c for c in comps)
        # A player with all-zero components has no meaningful ESPN price;
        # treat as incomplete so zero-projections don't pollute pools.
        has_price = any(v != 0 for v in comps.values())
        complete = pos in NEED and has_price and all(c in comps for c in NEED[pos])

        espn_ros = {s: round(fantasy_points(comps, s), 2) for s in SCORINGS}
        espn_ppg = {s: round(espn_ros[s] / gr, PPG_DECIMALS) for s in SCORINGS}

        p["espn_complete"] = bool(complete)
        p["espn_comp_count"] = len(covered)
        p["espn_covered"] = covered
        if has_price:
            p["espn_ros"] = espn_ros
            p["espn_ppg"] = espn_ppg
        else:
            # No ESPN price: clear the fields so downstream pools skip them.
            p.pop("espn_ros", None)
            p.pop("espn_ppg", None)
        if complete:
            # ESPN where priced, no ECR fill needed.
            p["espn_filled_ros"] = dict(espn_ros)
            p["espn_filled_ppg"] = dict(espn_ppg)
        # else: preserve existing ECR-filled values (fresh ECR unavailable).
        if complete:
            n_complete += 1
        n_updated += 1

    # Recompute deltas vs the (unchanged) ECR leg.
    for p in players:
        if p.get("espn_filled_ros") and p.get("ecr_ros"):
            p["delta_espn_ecr"] = round(
                p["espn_filled_ros"]["ppr"] - p["ecr_ros"]["ppr"], 2)
        if p.get("espn_filled_ppg") and p.get("ecr_ppg"):
            p["delta_espn_ecr_ppg"] = round(
                p["espn_filled_ppg"]["ppr"] - p["ecr_ppg"]["ppr"], 2)

    # Recompute the positional shade and adjusted fields (same math as bake).
    shade = {}
    for pos in ("QB", "RB", "WR", "TE"):
        vals = [r["ecr_ppg"]["ppr"] - r["espn_filled_ppg"]["ppr"] for r in players
                if r["pos"] == pos and r.get("ecr_ppg") and r.get("espn_filled_ppg")]
        shade[pos] = round(sum(vals) / len(vals), 3) if vals else 0.0
    for p in players:
        if p.get("delta_espn_ecr_ppg") is not None and p["pos"] in shade:
            p["delta_espn_ecr_ppg_demeaned"] = round(
                p["delta_espn_ecr_ppg"] - shade[p["pos"]], 2)
            p["espn_adj_ppg"] = round(
                (p.get("espn_filled_ppg") or {}).get("ppr", 0) + shade[p["pos"]], 2)

    meta["espn_snapshot"] = vintage
    meta["n_espn_complete"] = n_complete
    print(f"updated {n_updated} players ({n_complete} complete); shade={shade}")

    if args.dry_run:
        print("dry-run: not writing")
        return 0
    args.players.write_text(json.dumps(players_doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.players}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
