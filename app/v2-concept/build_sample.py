#!/usr/bin/env python3
"""Build app/v2-concept/sample.js from the comparison fixture.

Reads dist/modules/player-trace.json (rescaled chart values, full PPR,
12 teams) and name, position and team from data/fixtures/current/players.json.
One chart is stored under full_12_qb1; the others use full_12.

Market is the mean of those four indexed trade charts, before any
position-weight adjustment. The preview uses that mean as DDF Charted
Value (your side) and as the Market (their side). The `ddf` field is
one projection source on the value scale, the DDF Projected Value
stand-in. Publisher names are not written into the sample. This does
not compute live DDF Charted Value.

Run from the repo root: python3 app/v2-concept/build_sample.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "dist" / "modules" / "player-trace.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
OUT = Path(__file__).resolve().parent / "sample.js"

# Keys stay in the builder so the mean is reproducible. They are not
# copied into sample.js, and the preview never prints them.
CHARTS = [
    ("fantasycalc", "full_12_qb1"),
    ("fantasypros", "full_12"),
    ("usatoday", "full_12"),
    ("cbs", "full_12"),
]

# Recognizable skill players. Quarterbacks are left out on purpose: on the
# 1QB chart scale a raw gap against the projection anchor overstates the lead.
WANTED = [
    "Puka Nacua",
    "Jaxon Smith-Njigba",
    "Jahmyr Gibbs",
    "Bijan Robinson",
    "Ja'Marr Chase",
    "Christian McCaffrey",
    "Amon-Ra St. Brown",
    "CeeDee Lamb",
    "Justin Jefferson",
    "Jonathan Taylor",
    "Derrick Henry",
    "Drake London",
    "Malik Nabers",
    "Brock Bowers",
    "Chris Olave",
    "Breece Hall",
    "Josh Jacobs",
    "Nico Collins",
    "George Kittle",
    "Sam LaPorta",
    "Ashton Jeanty",
    "Bucky Irving",
    "Chase Brown",
    "Jaylen Warren",
    "Tetairoa McMillan",
]


def reindexed(sources: dict, key: str, combo: str):
    cell = (sources.get(key) or {}).get("combos", {}).get(combo)
    if not cell:
        return None
    value = cell.get("fixture_reindexed")
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 1)


def mean_1(values: list[float]) -> float:
    return round(sum(values) / len(values), 1)


def r1(value: float) -> float:
    return round(float(value), 1)


def points_for(info: dict) -> dict:
    """Full-PPR rest-of-season points. Three reads, then their average.

    ESPN and Razzball store a rest-of-season total. CBS stores a per-game
    rate, so its rest-of-season total is that rate times games remaining.
    """
    games = info.get("games_remaining")
    if not isinstance(games, (int, float)) or games <= 0:
        raise SystemExit(f"no games remaining for {info.get('name')}")
    espn_ppg = info["espn_ppg"]["ppr"]
    espn_ros = info["espn_ros"]["ppr"]
    cbs_ppg = info["cbsros_ppg"]["ppr"]
    rz_ppg = info["rz_ppg"]["ppr"]
    rz_ros = info["rz_ros"]["ppr"]
    cbs_ros = float(cbs_ppg) * float(games)
    return {
        "ppg": r1((float(espn_ppg) + float(cbs_ppg) + float(rz_ppg)) / 3),
        "ros": r1((float(espn_ros) + cbs_ros + float(rz_ros)) / 3),
        "reads": [
            {"name": "ESPN", "ppg": r1(espn_ppg), "ros": r1(espn_ros)},
            {"name": "CBS, rest of season", "ppg": r1(cbs_ppg), "ros": r1(cbs_ros)},
            {"name": "Razzball", "ppg": r1(rz_ppg), "ros": r1(rz_ros)},
        ],
    }


def main() -> None:
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    roster = json.loads(PLAYERS.read_text(encoding="utf-8"))
    by_key = {player["player_key"]: player for player in roster["players"]}
    found = {}
    for player in trace["players"]:
        info = by_key.get(player["player_key"], {})
        name = info.get("name") or player["name"]
        if name in WANTED:
            found[name] = (player, info)

    missing = [name for name in WANTED if name not in found]
    if missing:
        raise SystemExit(f"missing players: {missing}")

    rows = []
    for name in WANTED:
        player, info = found[name]
        charts = [reindexed(player["sources"], key, combo) for key, combo in CHARTS]
        ddf = reindexed(player["sources"], "espn", "full_12")
        if ddf is None or any(value is None for value in charts):
            raise SystemExit(f"incomplete row: {name} ddf={ddf} charts={charts}")
        market = mean_1(charts)
        rows.append({
            "id": player["player_key"],
            "name": name,
            "pos": info.get("pos"),
            "team": info.get("team"),
            "ddf": ddf,
            "market": market,
            "gap": round(ddf - market, 1),
            "capped": ddf >= 69.9,
            "points": points_for(info),
        })

    feature_buy = max(
        (row for row in rows if row["gap"] > 0 and not row["capped"]),
        key=lambda row: row["gap"],
    )
    feature_sell = min(
        (row for row in rows if row["gap"] < 0),
        key=lambda row: row["gap"],
    )
    # Give Puka, get McCaffrey. Charts, the value-scale points read, and
    # the weekly points all say you give value up. They improve on the
    # Market. The verdict is Don't do it.
    give = next(row for row in rows if row["name"] == "Puka Nacua")
    get = next(row for row in rows if row["name"] == "Christian McCaffrey")
    my_gain = round(get["ddf"] - give["ddf"], 1)
    their_market = round(give["market"] - get["market"], 1)

    payload = {
        "asOf": "2026-10-26",
        "setting": "Full PPR, 12 teams",
        "scaleMax": 80,
        "leagueTeams": 12,
        "leaguePlayers": 186,
        "featured": {
            "buy": feature_buy["id"],
            "sell": feature_sell["id"],
            "give": give["id"],
            "get": get["id"],
        },
        "players": rows,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    header = (
        "/* Generated by app/v2-concept/build_sample.py. Do not hand-edit numbers.\n"
        "   Market is the mean of the indexed trade charts. That mean is\n"
        "   DDF Charted Value and, from the other side, the Market.\n"
        "   The ddf field is one projection source on the value scale,\n"
        "   the DDF Projected Value stand-in. Publisher names are absent. */\n"
        "window.CONCEPT_SAMPLE = "
    )
    OUT.write_text(header + body + ";\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} players)")
    print(f"feature buy {feature_buy['name']} gap {feature_buy['gap']} ddf {feature_buy['ddf']} market {feature_buy['market']}")
    print(f"feature sell {feature_sell['name']} gap {feature_sell['gap']} ddf {feature_sell['ddf']} market {feature_sell['market']}")
    print(f"sample trade give {give['name']} (ddf {give['ddf']}, market {give['market']})")
    print(f"             get  {get['name']} (ddf {get['ddf']}, market {get['market']})")
    chart_gain = round(get["market"] - give["market"], 1)
    print(f"chart DDF {chart_gain}; projection-series {my_gain}; their Market change {their_market}")
    print(
        "projection ppg "
        f"{give['points']['ppg']} -> {get['points']['ppg']} "
        f"({round(get['points']['ppg'] - give['points']['ppg'], 1)}), "
        "ros "
        f"{give['points']['ros']} -> {get['points']['ros']} "
        f"({round(get['points']['ros'] - give['points']['ros'], 1)})"
    )
    ranked = sorted(rows, key=lambda row: -row["gap"])
    for row in ranked[:8]:
        cap = " capped" if row["capped"] else ""
        print(f"  {row['gap']:+5.1f}  {row['name']}{cap}")


if __name__ == "__main__":
    main()
