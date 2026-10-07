"""Canonical calibration loop: score projection sources vs actuals.

For every final game that has both projection snapshots and loaded stats,
takes the latest snapshot per (player, game, source, scoring format) and
scores MAE / RMSE / bias against v_player_game_actuals.

Writes one ranker_performance row per (source, scoring_format, week) with
the metrics in metadata. Idempotent per week: deletes existing rows for
the (season, week) before writing.

Usage: python3 bin/calibrate.py [--season 2026] [--week N]
  No --week: scores all final games with stats.
"""
import argparse
import math
import os
import sys
import uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import sbclient  # noqa: E402
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-mgmt/bin"))
import mgmt  # noqa: E402

ACT_COL = {"full_ppr": "actual_ppr", "half_ppr": "actual_half",
           "standard": "actual_std"}


def score(season=None, week=None):
    clauses = ["g.status='final'"]
    if season:
        clauses.append(f"g.season={int(season)}")
    if week:
        clauses.append(f"g.week={int(week)}")
    where = " AND ".join(clauses)

    rows = mgmt.query(f"""
        WITH latest AS (
          SELECT DISTINCT ON (ps.player_id, ps.game_id, ps.source, ps.scoring_format)
                 ps.player_id, ps.game_id, ps.source, ps.scoring_format,
                 ps.projected_points, g.season, g.week
          FROM projection_snapshots ps
          JOIN games g ON g.id = ps.game_id
          WHERE {where}
          ORDER BY ps.player_id, ps.game_id, ps.source, ps.scoring_format,
                   ps.snapshot_at DESC
        )
        SELECT l.source, l.scoring_format, l.season, l.week,
               l.projected_points AS proj,
               a.actual_ppr, a.actual_half, a.actual_std
        FROM latest l
        JOIN v_player_game_actuals a
          ON a.player_id = l.player_id AND a.game_id = l.game_id
        WHERE l.projected_points IS NOT NULL;
    """)

    # group by (source, format, season, week)
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        act = r[ACT_COL[r["scoring_format"]]]
        if act is None:
            continue
        groups[(r["source"], r["scoring_format"], r["season"], r["week"])].append(
            (float(r["proj"]), float(act)))

    results = []
    for (source, fmt, sn, wk), pairs in sorted(groups.items()):
        n = len(pairs)
        errs = [p - a for p, a in pairs]
        mae = sum(abs(e) for e in errs) / n
        rmse = math.sqrt(sum(e * e for e in errs) / n)
        bias = sum(errs) / n
        results.append({"source": source, "format": fmt, "season": sn,
                        "week": wk, "n": n,
                        "mae": round(mae, 3), "rmse": round(rmse, 3),
                        "bias": round(bias, 3)})
    return results


def ranker_id_for(source):
    name = {"vegas_implied": "Vegas implied", "espn": "ESPN",
            "fantasypros": "FantasyPros"}.get(source, source)
    found = sbclient.get("rankers", f"?select=id&display_name=eq.{name}&limit=1")
    if found:
        return found[0]["id"]
    rid = str(uuid.uuid4())
    sbclient.post("rankers", [{"id": rid, "display_name": name,
                               "affiliation": source, "active": True}])
    return rid


def persist(results):
    # Idempotent per (ranker, season, week): delete ONCE per key before
    # inserting that key's formats. (Bug fixed 2026-09-12: the old loop
    # deleted per result row, so each scoring format's insert wiped the
    # previous format's row for the same source/week — only the last
    # format survived. The table's unique key is now
    # (ranker_id, season, week, scoring_format), so all formats persist.)
    deleted = set()
    for r in results:
        rid = ranker_id_for(r["source"])
        key = (rid, r["season"], r["week"])
        if key not in deleted:
            mgmt.query(
                "DELETE FROM ranker_performance WHERE ranker_id='%s' "
                "AND season=%d AND week=%d;" % (rid, r["season"], r["week"]))
            deleted.add(key)
        mgmt.query(
            """INSERT INTO ranker_performance
               (id, ranker_id, season, week, scoring_format,
                accuracy_score, metadata)
               VALUES ('%s','%s',%d,%d,'%s',%s,'%s');""" % (
                str(uuid.uuid4()), rid, r["season"], r["week"], r["format"],
                r["mae"],
                ("{\"scoring_format\": \"%s\", \"rmse\": %s, \"bias\": %s, \"n\": %d}"
                 % (r["format"], r["rmse"], r["bias"], r["n"])).replace("'", "''")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--no-persist", action="store_true")
    a = ap.parse_args()
    results = score(a.season, a.week)
    if not results:
        print("no scored games (need final games with snapshots + stats)")
        return
    for r in results:
        print(f"{r['source']:12s} {r['format']:9s} s{r['season']}w{r['week']}: "
              f"n={r['n']:3d} MAE={r['mae']:.2f} RMSE={r['rmse']:.2f} "
              f"bias={r['bias']:+.2f}")
    if not a.no_persist:
        persist(results)
        print(f"persisted {len(results)} rows to ranker_performance")


if __name__ == "__main__":
    main()
