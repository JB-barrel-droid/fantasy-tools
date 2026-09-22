"""Fetch ESPN fantasy projections for a scoring period (week).

Uses the public ESPN fantasy API players_wl view:
  https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players
    ?scoringPeriodId={week}&view=players_wl
No auth needed. Paginates with X-Fantasy-Filter until exhausted.

Output: data/espn_wk{N}_full.json — a list of raw player objects, each
with fullName and stats[] ({scoringPeriodId, statSplitTypeId, stats}).
Same shape the v4 engine's load_espn_full() already reads.

Usage: python3 fetch_espn.py [--week N] [--season 2026]
  --week defaults to engine.week.current_week().
"""
import argparse
import json
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
sys.path.insert(0, os.path.join(BASE, "engine"))
from week import current_week  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch_week(season: int, week: int) -> list:
    url = (f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players"
           f"?scoringPeriodId={week}&view=players_wl")
    out, offset, limit = [], 0, 1000
    while True:
        filt = json.dumps({"players": {"limit": limit, "offset": offset}})
        req = urllib.request.Request(url, headers={**UA, "X-Fantasy-Filter": filt})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
        if not body.strip().startswith(b"{"):
            raise RuntimeError(
                "ESPN returned HTML instead of JSON (bot protection). "
                "Fetch this week's file with a real browser session instead, "
                f"save it as data/espn_wk{week}_full.json, and rerun.")
        data = json.loads(body)
        batch = [p["player"] for p in data.get("players", []) if "player" in p]
        out.extend(batch)
        print(f"offset {offset}: {len(batch)} players", flush=True)
        if len(batch) < limit:
            break
        offset += limit
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    week = a.week or current_week(a.season)
    players = fetch_week(a.season, week)
    # keep only players with a projected stat line for this week
    proj = [p for p in players if any(
        s.get("scoringPeriodId") == week and s.get("statSplitTypeId") == 1
        for s in p.get("stats", []))]
    path = os.path.join(BASE, "data", f"espn_wk{week}_full.json")
    json.dump(players, open(path, "w"))
    print(f"saved {len(players)} players ({len(proj)} with week-{week} projections) -> {path}")


if __name__ == "__main__":
    main()
