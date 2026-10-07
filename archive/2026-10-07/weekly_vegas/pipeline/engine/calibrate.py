"""Calibration: score frozen pre-game projections against actuals.

Joins projection_snapshots -> player_game_stats (post-game). Games not yet
played (no actuals row) are skipped. Prints MAE, RMSE, and mean bias
(projected minus actual; positive => source over-projects) grouped by source,
then by source x position.

Read-only.
"""
import math
import os
import sys
from collections import defaultdict

SB = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
for p in (SB, BASE):
    if p not in sys.path:
        sys.path.insert(0, p)
import sbclient  # noqa: E402

from engine.scoring import fantasy_points  # noqa: E402


def actual_points(stats_row, scoring_format):
    """player_game_stats.fantasy_points is PPR; recompute other formats."""
    if scoring_format == "full_ppr":
        return float(stats_row["fantasy_points"])
    stats = {k: float(v or 0) for k, v in (stats_row.get("stats") or {}).items()}
    return fantasy_points(stats, {"standard": "standard",
                                  "half_ppr": "half_ppr"}[scoring_format])


def main():
    try:
        snaps = sbclient.get_all("projection_snapshots", "?select=*&limit=100000")
    except Exception as e:
        if "PGRST205" in str(e):
            print("projection_snapshots table does not exist yet — nothing to score.")
            return
        raise
    if not snaps:
        print("no snapshots stored yet.")
        return

    pairs = {(s["player_id"], s["game_id"]) for s in snaps}
    stats_rows = sbclient.get_all("player_game_stats",
                                  "?select=player_id,game_id,stats,fantasy_points&limit=100000")
    actual = {(r["player_id"], r["game_id"]): r for r in stats_rows}

    players = {p["id"]: p for p in
               sbclient.get_all("players", "?select=id,position,full_name&limit=20000")}

    errs = defaultdict(list)  # (source, pos) -> [proj - actual]
    skipped = 0
    for s in snaps:
        key = (s["player_id"], s["game_id"])
        a = actual.get(key)
        if not a:
            skipped += 1
            continue
        try:
            act = actual_points(a, s["scoring_format"])
        except Exception:
            skipped += 1
            continue
        pos = (players.get(s["player_id"]) or {}).get("position", "?")
        errs[(s["source"], pos)].append(float(s["projected_points"]) - act)

    if not errs:
        print(f"no completed games yet ({skipped} snapshot rows awaiting actuals).")
        return

    def agg(v):
        n = len(v)
        mae = sum(abs(x) for x in v) / n
        rmse = math.sqrt(sum(x * x for x in v) / n)
        bias = sum(v) / n
        return n, mae, rmse, bias

    # by source
    by_src = defaultdict(list)
    for (src, _), v in errs.items():
        by_src[src].extend(v)
    print(f"{'source':14s} {'n':>6s} {'MAE':>7s} {'RMSE':>7s} {'bias':>7s}")
    for src in sorted(by_src):
        n, mae, rmse, bias = agg(by_src[src])
        print(f"{src:14s} {n:6d} {mae:7.2f} {rmse:7.2f} {bias:+7.2f}")
    print()
    print(f"{'source x pos':20s} {'n':>6s} {'MAE':>7s} {'RMSE':>7s} {'bias':>7s}")
    for (src, pos) in sorted(errs):
        n, mae, rmse, bias = agg(errs[(src, pos)])
        print(f"{src + ' / ' + pos:20s} {n:6d} {mae:7.2f} {rmse:7.2f} {bias:+7.2f}")
    print(f"\n({skipped} rows skipped: games not yet played)")


if __name__ == "__main__":
    main()
