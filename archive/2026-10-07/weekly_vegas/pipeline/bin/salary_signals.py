"""DK salary vs ECR disagreement report.

Salaries are a second market signal alongside Vegas-implied points:
within each position, rank players by DK salary and compare to their
position-specific ECR. A big rank gap = the DFS market disagrees with
the experts — the same family as the prop-implied signals.

Outputs data/salary_signals.json with the same gate shape as the
prop signals (>=8 rank gap, floor on salary rank).
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-football-signal/bin"))
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-mgmt/bin"))

import mgmt  # noqa: E402
from engine.snapshot import norm  # noqa: E402


def main(week=None, season=2026):
    if week is None:
        from engine.week import current_week
        week = current_week(season)
    ecr = json.load(open(os.path.join(BASE, "data", "ecr_pos.json")))
    # ecr: norm name -> {name, pos, team, pos_rank, rank_ecr, ...}

    rows = mgmt.query(f"""
        select player_name, position, team, salary
        from dfs_salaries
        where season={season} and week={week} and player_id is not null
        order by salary desc;""")
    # shared universe only: players present in BOTH salary and ECR.
    # (ECR ranks far deeper than DK prices anyone, so raw rank scales differ.)
    shared = [r for r in rows if norm(r["player_name"]) in ecr]
    by_pos = {}
    for r in shared:
        by_pos.setdefault(r["position"], []).append(r)
    sal_rank = {}
    for pos, lst in by_pos.items():
        for i, r in enumerate(lst, 1):
            sal_rank[norm(r["player_name"])] = (i, r)

    # ECR rank re-ranked within the shared universe (same scale fix)
    ecr_rank = {}
    by_pos_ecr = {}
    for r in shared:
        e = ecr[norm(r["player_name"])]
        by_pos_ecr.setdefault(e.get("pos"), []).append(
            (e.get("pos_rank", 999), norm(r["player_name"])))
    for pos, lst in by_pos_ecr.items():
        for i, (_, key) in enumerate(sorted(lst), 1):
            ecr_rank[key] = i

    out = []
    for key, (srank, r) in sal_rank.items():
        e = ecr.get(key)
        erank = ecr_rank.get(key)
        if not erank:
            continue
        # gates: ignore minimum-salary scrubs
        if r["salary"] < 4000:
            continue
        gap = erank - srank  # positive: market (salary) higher on player
        if abs(gap) >= 8:
            out.append({
                "name": e.get("name"), "pos": e.get("pos"),
                "team": e.get("team"), "salary": r["salary"],
                "salary_rank": srank, "ecr_pos_rank": erank,
                "rank_gap": gap,
                "direction": "LOVE" if gap > 0 else "FADE",
            })
    out.sort(key=lambda x: -abs(x["rank_gap"]))
    path = os.path.join(BASE, "data", "salary_signals.json")
    json.dump(out, open(path, "w"), indent=1)
    loves = sum(1 for x in out if x["direction"] == "LOVE")
    print(f"salary signals: {len(out)} ({loves} LOVE, "
          f"{len(out) - loves} FADE) -> {path}", flush=True)
    for x in out[:8]:
        print(f"  {x['direction']:4s} {x['name']} ({x['pos']},{x['team']}) "
              f"sal#{x['salary_rank']} vs ecr#{x['ecr_pos_rank']} "
              f"${x['salary']:,}", flush=True)
    return out


if __name__ == "__main__":
    main()
