"""Build the JEG-1240 USO-shape journey league (synthetic rosters, real player keys).

Repro:  python3 tests/fixtures/uso_site_journey/build_fixture.py

What it is: a 12-team, half-PPR league with the USO roster *shape* (QB 1, RB 2,
WR 3, TE 1, W/R/T 1, K 1, DEF 1, BN 5; 15 per team). The shape is the only thing
taken from USO: it is the `roster_slots` / `teams_count` that #1105 recorded from
the league settings on 2026-10-29 (Yahoo via Flaim, read only). No USO roster,
team name, owner or note is used. The rosters are a deterministic snake draft of
`data/fixtures/current/players.json` (active-roster skill players, ordered by the
ESPN half-PPR rest-of-season projection the file carries), with one swap so that
Jaxon Smith-Njigba (key 3247) is on the user's team, which is the case JEG-1240
pins. K and DEF are "x:" entries (not evaluated, as on the site).

Values are not frozen here: the render test prices these keys with whatever the
built page publishes, and the Node contract prices them with modeled rows. Both
say so in their output.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "league.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

TEAMS = 12
PER_TEAM = {"QB": 2, "RB": 4, "WR": 5, "TE": 2}
JSN = "3247"
MINE = 0
NFL = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB"]


def snake(pool: list[dict], rounds: int) -> list[list[dict]]:
    out: list[list[dict]] = [[] for _ in range(TEAMS)]
    for r in range(rounds):
        order = range(TEAMS) if r % 2 == 0 else range(TEAMS - 1, -1, -1)
        for i, t in enumerate(order):
            out[t].append(pool[r * TEAMS + i])
    return out


def build() -> dict:
    data = json.loads(PLAYERS.read_text(encoding="utf-8"))
    rows = [p for p in data["players"] if p["pos"] in PER_TEAM and p.get("roster_status") == "active_roster"
            and isinstance((p.get("blend_ros") or {}).get("half_ppr"), (int, float))]
    teams: list[list[dict]] = [[] for _ in range(TEAMS)]
    for pos, n in PER_TEAM.items():
        pool = sorted((p for p in rows if p["pos"] == pos), key=lambda p: (-p["blend_ros"]["half_ppr"], p["player_key"]))
        for t, picks in enumerate(snake(pool, n)):
            teams[t].extend(picks)
    holder = next(t for t, ps in enumerate(teams) if any(str(p["player_key"]) == JSN for p in ps))
    if holder != MINE:
        mine_wr = next(p for p in teams[MINE] if p["pos"] == "WR")
        jsn = next(p for p in teams[holder] if str(p["player_key"]) == JSN)
        teams[MINE][teams[MINE].index(mine_wr)] = jsn
        teams[holder][teams[holder].index(jsn)] = mine_wr
    league = []
    for t, ps in enumerate(teams):
        players = [{"key": str(p["player_key"]), "name": p["name"], "pos": p["pos"], "team": p.get("team") or ""} for p in ps]
        players.append({"key": f"x:K:kicker-{t + 1:02d}", "name": f"Kicker {t + 1:02d}", "pos": "K", "team": ""})
        players.append({"key": f"x:DEF:{NFL[t]}", "name": f"{NFL[t]} D/ST", "pos": "DEF", "team": NFL[t]})
        league.append({"name": "My team" if t == MINE else f"Team {t + 1:02d}", "players": players})
    return {
        "fixture": "uso_site_journey",
        "note": ("Synthetic rosters in the USO roster shape (JEG-1240). Not USO's rosters: snake draft of "
                 "data/fixtures/current/players.json, rebuild with build_fixture.py. Values come from the page at test time."),
        "shape_source": "USO league settings, roster_slots and teams_count as recorded 2026-10-29 in #1105 (shape only)",
        "players_as_of": data["meta"]["as_of"],
        "settings": {"scoring": "half_ppr", "teams": TEAMS,
                     "roster": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 5, "K": 1, "DST": 1}},
        "myTeamIndex": MINE,
        "focus": {"key": JSN, "name": "Jaxon Smith-Njigba"},
        "teams": league,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
