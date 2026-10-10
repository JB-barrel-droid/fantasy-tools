#!/usr/bin/env python3
"""What weekly history does ESPN's fantasy API serve for past seasons? (JEG-521 G4 d)

Read-only probe, run by espn-history-probe.yml (manual). For each season it
asks the same endpoint the ESPN leg uses (leaguedefaults/3, kona_player_info)
for the top 25 RBs, once for actuals (statSourceId 0) and once for
projections (statSourceId 1), and counts the stat blocks it gets back by
(seasonId, statSourceId, statSplitTypeId, scoringPeriodId). It also tries the
same request with scoringPeriodId set to one week, which some seasons need.

A season "serves weekly projections" when split-1 projection blocks exist
for at least 15 of its weeks. Output: output/espn-history-probe.json and a
short markdown table on stdout.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "espn-history-probe.json"
HOSTS = ("https://lm-api-reads.fantasy.espn.com", "https://fantasy.espn.com")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "X-Fantasy-Source": "kona", "X-Fantasy-Platform": "kona-web"}
SEASONS = list(range(2018, 2026))


def fetch(host, season, source, scoring_period=0, limit=25):
    url = (f"{host}/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3"
           f"?scoringPeriodId={scoring_period}&view=kona_player_info")
    filt = {"players": {"filterSlotIds": {"value": [2]},
                        "filterStatsForSourceIds": {"value": [source]},
                        "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
                        "limit": limit, "offset": 0}}
    h = dict(UA, **{"X-Fantasy-Filter": json.dumps(filt)})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def summarize(payload, season):
    blocks = Counter()
    players = payload.get("players") or []
    for p in players:
        for s in (p.get("player") or {}).get("stats") or []:
            blocks[(s.get("seasonId"), s.get("statSourceId"), s.get("statSplitTypeId"),
                    s.get("scoringPeriodId"))] += 1
    weeks = lambda src: sorted({k[3] for k in blocks if k[0] == season and k[1] == src  # noqa: E731
                                and k[2] == 1 and isinstance(k[3], int) and k[3] >= 1})
    return {"players": len(players),
            "weekly_actual_weeks": weeks(0), "weekly_projection_weeks": weeks(1),
            "season_blocks": sorted({f"src{k[1]}/split{k[2]}" for k in blocks
                                     if k[0] == season and k[3] == 0}),
            "other_season_ids": sorted({k[0] for k in blocks if k[0] != season})}


def main() -> int:
    results, errors = {}, []
    for season in SEASONS:
        res = {}
        for host in HOSTS:
            for source in (0, 1):
                for sp in (0, 8):
                    key = f"{host.split('//')[1].split('.')[0]}/src{source}/period{sp}"
                    try:
                        res[key] = summarize(fetch(host, season, source, sp), season)
                    except urllib.error.HTTPError as e:
                        res[key] = {"error": f"HTTP {e.code}"}
                    except Exception as e:  # noqa: BLE001
                        res[key] = {"error": f"{type(e).__name__}: {e}"[:200]}
                    time.sleep(0.4)
            if any("error" not in v for v in res.values()):
                break  # first host that answers is enough
        results[season] = res
    verdict = {}
    for season, res in results.items():
        proj = max((len(v.get("weekly_projection_weeks", [])) for v in res.values()), default=0)
        act = max((len(v.get("weekly_actual_weeks", [])) for v in res.values()), default=0)
        verdict[season] = {"weekly_projection_weeks": proj, "weekly_actual_weeks": act,
                           "serves_weekly_projections": proj >= 15,
                           "serves_weekly_actuals": act >= 15}
    doc = {"about": __doc__.split("\n")[0], "verdict": verdict, "detail": results,
           "errors": errors, "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n")
    print("| Season | Weekly projection weeks | Weekly actual weeks |")
    print("| -- | -- | -- |")
    for s, v in verdict.items():
        print(f"| {s} | {v['weekly_projection_weeks']} | {v['weekly_actual_weeks']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
