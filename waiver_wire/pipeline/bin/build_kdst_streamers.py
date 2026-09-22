#!/usr/bin/env python3
"""Enrich the draft waiver-dashboard artifact's baked K/DST streamer data.

Adds ESPN roster% (pulled 2026-09-16 via lottery/engine/espn_roster.py,
lineup slots K=17 / DST=16) and Week 2 opponents (nflverse schedules) to
each record in the artifact's inline `streamerData` blob.

Projections and chart_value are carried through UNCHANGED - this step only
adds fields. Fail-closed: a kicker name that does not resolve in the ESPN
lookup, a DST team that does not map to an ESPN abbreviation, or a streamer
team missing from the week schedule aborts the write (no partial bake).

Usage: bin/build_kdst_streamers.py [WEEK]   (default WEEK=2)

K/DST stay out of Hot pickups / Adds / Holds / Drops by design; this only
touches the standalone K/DST Streamers section data.
"""
import json
import re
import sys
from pathlib import Path

LOT = Path(__file__).resolve().parent.parent  # waiver_wire/pipeline
sys.path.insert(0, str(LOT / "engine"))
import espn_roster  # noqa: E402

ARTIFACT = LOT.parent.parent / "waiver_wire" / "dashboard" / "index.html"
DATE_TAG = "2026-09-16"

# Streamer-side team abbr -> ESPN mascot abbr. Only LAR differs today;
# anything else unmapped aborts (fail-closed, don't guess).
TEAM_TO_ESPN = {"LAR": "LA"}

WEEK = int(sys.argv[1]) if len(sys.argv) > 1 else 2


def week_opponents(week):
    """team abbr -> (opponent abbr, is_home) for the given NFL week."""
    from nflreadpy import load_schedules

    import polars as pl

    sched = load_schedules([2026]).filter(
        (pl.col("season") == 2026) & (pl.col("week") == week)
    )
    games = sched.select("home_team", "away_team").to_dicts()
    if len(games) != 16:
        raise RuntimeError(
            f"week {week} schedule has {len(games)} games, expected 16 - "
            "refusing to bake opponents"
        )
    opp = {}
    for g in games:
        home, away = g["home_team"], g["away_team"]
        opp[home] = (away, True)
        opp[away] = (home, False)
    return opp


def main():
    html = ARTIFACT.read_text()
    m = re.search(r"const streamerData = (\{.*?\});\n", html)
    if not m:
        raise RuntimeError("streamerData blob not found in artifact")
    data = json.loads(m.group(1))

    lookup = espn_roster.build_lookup(date_tag=DATE_TAG)
    opponents = week_opponents(WEEK)

    enriched = dict(data)
    enriched["fetched"] = DATE_TAG
    enriched["roster_pct_source"] = "ESPN %ROST (slots K=17, DST=16)"

    ks = []
    for rec in data["kickers"]:
        key = espn_roster.norm_name(rec["name"])
        if key not in lookup:
            raise KeyError(f"kicker {rec['name']!r} not in ESPN roster lookup")
        team = rec["team"]
        sched_team = TEAM_TO_ESPN.get(team, team)
        if sched_team not in opponents:
            raise KeyError(f"kicker team {team!r} not in week {WEEK} schedule")
        opp, home = opponents[sched_team]
        ks.append({
            **rec,
            "opponent": opp,
            "home": home,
            "roster_pct": lookup[key],
        })

    ds = []
    for rec in data["defenses"]:
        team = rec["team"]
        espn_abbr = TEAM_TO_ESPN.get(team, team)
        if espn_abbr not in espn_roster.MASCOT_ABBR.values():
            raise KeyError(f"DST team {team!r} maps to unknown ESPN abbr {espn_abbr!r}")
        key = "dst:" + espn_abbr.lower()
        if key not in lookup:
            raise KeyError(f"DST {rec['name']!r} not in ESPN roster lookup (key {key})")
        if espn_abbr not in opponents:
            raise KeyError(f"DST team {team!r} not in week {WEEK} schedule")
        opp, home = opponents[espn_abbr]
        ds.append({
            **rec,
            "opponent": opp,
            "home": home,
            "roster_pct": lookup[key],
        })

    enriched["kickers"] = ks
    enriched["defenses"] = ds

    blob = "const streamerData = " + json.dumps(enriched, separators=(",", ":")) + ";\n"
    new_html = html[: m.start()] + blob + html[m.end():]
    ARTIFACT.write_text(new_html)
    print(f"baked roster% + week {WEEK} opponents into {len(ks)} kickers, "
          f"{len(ds)} defenses ({ARTIFACT})")


if __name__ == "__main__":
    main()
