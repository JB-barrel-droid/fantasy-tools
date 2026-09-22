"""Build per-type ECR JSON files from ranker_rankings.

Reads the FantasyPros {Weekly,Draft,ROS,Dynasty} ECR rankers and writes:
  data/ecr_weekly.json, data/ecr_draft.json, data/ecr_ros.json,
  data/ecr_dynasty.json
plus data/ecr_pos.json (weekly, kept for backward compat with the readers
that expect it: compute_v4, salary_signals, news, snapshot).

Shape (same as the legacy ecr_pos.json): norm name ->
  {name, pos, team, pos_rank_str, pos_rank, rank_ecr, experts}

For weekly/ros the latest week is used; draft/dynasty are week 0.
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

ECR_TYPES = ["weekly", "draft", "ros", "dynasty"]


def build(ecr_type, season=2026, week=None):
    rankers = mgmt.query(
        f"select id, display_name from rankers where ecr_type='{ecr_type}';")
    if not rankers:
        return None, f"no {ecr_type} rankers"
    rids = ",".join(f"'{r['id']}'" for r in rankers)
    if week is None:
        w = mgmt.query(
            f"select max(week) m from ranker_rankings "
            f"where ranker_id in ({rids}) and season={season};")[0]["m"]
        if w is None:
            return None, f"no {ecr_type} rows"
        week = w
    rows = mgmt.query(f"""
        select rr.player_id, rr.position_rank, rr.ranking, rr.projected_points,
               p.full_name, p.position, t.abbreviation as team
        from ranker_rankings rr
        join players p on p.id = rr.player_id
        left join teams t on t.id = p.team_id
        where rr.ranker_id in ({rids}) and rr.season={season}
          and rr.week={week};""")
    out = {}
    for r in rows:
        pos = (r["position"] or "").upper()
        pr = r["position_rank"]
        out[norm(r["full_name"] or "")] = {
            "name": r["full_name"], "pos": pos, "team": r["team"],
            "pos_rank_str": f"{pos}{pr}" if pr else None,
            "pos_rank": pr, "rank_ecr": r["ranking"],
            "experts": None,
        }
    return out, None


def main(season=2026):
    for t in ECR_TYPES:
        out, err = build(t, season)
        if err:
            print(f"ecr_{t}: {err}")
            continue
        path = os.path.join(BASE, "data", f"ecr_{t}.json")
        json.dump(out, open(path, "w"), indent=1)
        print(f"ecr_{t}: {len(out)} players -> {path}")
    # backward compat: ecr_pos.json = weekly
    wk, err = build("weekly", season)
    if not err:
        json.dump(wk, open(os.path.join(BASE, "data", "ecr_pos.json"), "w"),
                  indent=1)
        print("ecr_pos.json refreshed (weekly)")


if __name__ == "__main__":
    main()
