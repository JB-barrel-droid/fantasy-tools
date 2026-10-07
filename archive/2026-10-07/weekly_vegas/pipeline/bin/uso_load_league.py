#!/usr/bin/env python3
"""Load USO league snapshot into Supabase (yahoo_leagues/teams/rosters)
and compute trade_watch rows: need/surplus per team per position group
plus behavioral willingness signals."""
import json, sys
from datetime import date

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
from sbclient import post, get_all  # noqa: E402

SNAP_DATE = "2026-09-11"
LEAGUE_ID = "848938"

snap = json.load(open("/home/hatch/workspace/football-signal/data/yahoo_uso/snapshot_2026-09-11.json"))
audit = json.load(open("/home/hatch/workspace/football-signal/data/yahoo_uso/audit_2026-09-11.json"))
avg = audit["avg"]
taudit = audit["audit"]

# league
post("yahoo_leagues", [{"league_id": LEAGUE_ID, "name": snap["league"]["name"],
                        "season": snap["league"]["season"], "settings": snap["league"]}])
print("league upserted")

# teams
team_rows = []
for s in snap["standings"]:
    team_rows.append({"league_id": LEAGUE_ID, "snapshot_date": SNAP_DATE,
                      "team_name": s["team"], "manager": s["manager"],
                      "is_user": s.get("is_user", False), "w": s["w"], "l": s["l"], "t": s["t"],
                      "pf": s["pf"], "pa": s["pa"], "fab_remaining": s["fab"],
                      "waiver_order": s["waiver_order"], "moves": s["moves"],
                      "notes": "trade_list_note 2026-09-03" if s.get("trade_list_note") else None})
post("yahoo_teams", team_rows)
print(f"{len(team_rows)} teams loaded")

# rosters
ros_rows = []
for team, players in snap["rosters"].items():
    for pl in players:
        ros_rows.append({"league_id": LEAGUE_ID, "snapshot_date": SNAP_DATE, "team_name": team,
                         "player_name": pl["player"], "nfl_team": pl["nfl"], "position": pl["pos"],
                         "slot": pl["slot"], "status": pl["status"]})
post("yahoo_rosters", ros_rows)
print(f"{len(ros_rows)} roster rows loaded")

# trade_watch: need/surplus per position group + willingness signals
BEHAVIOR = {
    "Fear Boners": "posted trade wanted/offered note 2026-09-03; 4 waiver moves (churning WR/DEF)",
    "Noted Hana Guys": "Brock Bowers OUT -> starting Brenton Strange at TE (injury-forced need)",
    "Amon-Ra Martyr Brown": "3 waiver moves; Zach Charbonnet on PUP-R",
    "Tiny Hands": "5 waiver moves (most active); $7 FAB spent",
}
tw_rows = []
for team, a in taudit.items():
    for grp in ["QB", "RB", "WR", "TE", "FLEX"]:
        tv, av = a[grp], avg[grp]
        need = round(max(0, (av - tv) / av), 3)
        surplus = round(max(0, (tv - av) / av), 3)
        inj_forced = (team == "Noted Hana Guys" and grp == "TE") or \
                     (team == "Fear Boners" and grp == "WR")
        notes = []
        if need >= 0.10:
            notes.append(f"need: {tv} vs lg avg {av}")
        if surplus >= 0.10:
            notes.append(f"surplus: {tv} vs lg avg {av}")
        if inj_forced:
            notes.append("injury-forced")
        tw_rows.append({"league_id": LEAGUE_ID, "snapshot_date": SNAP_DATE, "team_name": team,
                        "position_group": grp, "need_score": need, "surplus_score": surplus,
                        "injury_forced": inj_forced,
                        "behavior_signal": BEHAVIOR.get(team),
                        "notes": "; ".join(notes) if notes else None})
post("trade_watch", tw_rows)
print(f"{len(tw_rows)} trade_watch rows loaded")

# verify
print("verify:", get_all("yahoo_rosters", f"?select=team_name&league_id=eq.{LEAGUE_ID}&snapshot_date=eq.{SNAP_DATE}&limit=1"))
print("trade_watch sample:", get_all("trade_watch",
      f"?select=team_name,position_group,need_score,surplus_score&league_id=eq.{LEAGUE_ID}&order=need_score.desc&limit=6"))
