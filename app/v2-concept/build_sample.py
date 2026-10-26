#!/usr/bin/env python3
"""Build app/v2-concept/sample.js from the comparison fixture.

Reads dist/modules/player-trace.json (fixture_reindexed, full PPR, 12 teams)
and name, position and team from data/fixtures/current/players.json.
FantasyCalc is stored under full_12_qb1; the other charts use full_12.

This is a design-preview sample. It does not compute DDF Value.
Run from the repo root: python3 app/v2-concept/build_sample.py
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "dist" / "modules" / "player-trace.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
OUT = Path(__file__).resolve().parent / "sample.js"

CHARTS = [
    ("fantasycalc", "full_12_qb1", "FantasyCalc"),
    ("fantasypros", "full_12", "FantasyPros"),
    ("usatoday", "full_12", "USA Today"),
    ("cbs", "full_12", "CBS"),
]

# Recognizable skill players. Quarterbacks are left out on purpose: on the
# 1QB chart scale a raw gap against the ESPN anchor overstates the lead.
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


def blurb_for(charts: dict, espn: float):
    """Group four charts into two camps when each camp is tight and they sit apart.

    Within a camp, the two values may differ by up to 8 points. The camps
    themselves must be at least 12 points apart. Otherwise, count how many
    charts sit above or below the projection read. This wording is for the
    preview only. It is not a trade-target rule.
    """
    items = [(label, charts[key]) for key, _, label in CHARTS]
    ordered = sorted(items, key=lambda item: item[1])
    low, high = ordered[:2], ordered[2:]
    camps = (
        high[0][1] - low[1][1] >= 12
        and low[1][1] - low[0][1] <= 8
        and high[1][1] - high[0][1] <= 8
    )
    if camps:
        def names(pair):
            pair = sorted(pair, key=lambda item: -item[1])
            return f"{pair[0][0]} and {pair[1][0]}"

        high_about = round((high[0][1] + high[1][1]) / 2)
        low_about = round((low[0][1] + low[1][1]) / 2)
        text = f"{names(high)} pay about {high_about}. {names(low)} pay about {low_about}."
        return text, "Charts are split", True

    priced = [value for _, value in items]
    below = sum(1 for value in priced if value < espn)
    above = sum(1 for value in priced if value > espn)
    if below == 4:
        return "Every chart pays less than the projection read.", "Every chart is lower", False
    if above == 4:
        return "Every chart pays more than the projection read.", "Every chart is higher", False
    if below > above:
        return f"{below} of 4 charts pay less than the projection read.", f"{below} of 4 charts are lower", False
    if above > below:
        return f"{above} of 4 charts pay more than the projection read.", f"{above} of 4 charts are higher", False
    return "The charts land on both sides of the projection read.", "Charts are mixed", False


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
        charts = {key: reindexed(player["sources"], key, combo) for key, combo, _ in CHARTS}
        espn = reindexed(player["sources"], "espn", "full_12")
        if espn is None or any(value is None for value in charts.values()):
            raise SystemExit(f"incomplete row: {name} espn={espn} charts={charts}")
        priced = list(charts.values())
        mid = round(float(median(priced)), 1)
        text, short, camps = blurb_for(charts, espn)
        rows.append({
            "id": player["player_key"],
            "name": name,
            "pos": info.get("pos"),
            "team": info.get("team"),
            "espn": espn,
            "mid": mid,
            "gap": round(espn - mid, 1),
            "charts": charts,
            "camps": camps,
            "blurb": text,
            "short": short,
            "capped": espn >= 69.9,
        })

    buys = [row for row in rows if row["gap"] > 0 and (row["camps"] or row["gap"] >= 2.5) and not row["capped"]]
    # Gibbs is capped at 70 and is still the right "light on" example. He is
    # eligible as a list member below; the featured buy skips the cap so the
    # first sentence is not sitting on the scale ceiling.
    feature_buy = max(
        (row for row in rows if row["gap"] > 0 and row["camps"] and not row["capped"]),
        key=lambda row: row["gap"],
    )
    feature_sell = min(
        (row for row in rows if row["gap"] < 0 and not row["camps"] and row["short"] == "Every chart is higher"),
        key=lambda row: row["gap"],
    )
    give = next(row for row in rows if row["name"] == "Puka Nacua")
    get = next(row for row in rows if row["name"] == "Jaxon Smith-Njigba")

    payload = {
        "asOf": "2026-10-26",
        "generatedAt": trace.get("generated_at"),
        "setting": "Full PPR, 12 teams",
        "scaleMax": 80,
        "publishers": [{"id": key, "name": label} for key, _, label in CHARTS],
        "source": "dist/modules/player-trace.json fixture_reindexed, names from data/fixtures/current/players.json",
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
        "   Comparison fixture, rescaled chart values, full PPR, 12 teams.\n"
        "   Not live DDF Value. */\n"
        "window.CONCEPT_SAMPLE = "
    )
    OUT.write_text(header + body + ";\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} players)")
    print(f"feature buy {feature_buy['name']} ({feature_buy['id']})")
    print(f"feature sell {feature_sell['name']} ({feature_sell['id']})")
    print(f"sample trade {give['name']} for {get['name']}")


if __name__ == "__main__":
    main()
