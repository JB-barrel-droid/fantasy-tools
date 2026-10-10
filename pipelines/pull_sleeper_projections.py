#!/usr/bin/env python3
"""Pull Sleeper's weekly fantasy projections, current and past seasons (JEG-540).

Internal measurement source only: never named on the site (CLAUDE.md
branding). Sleeper serves weekly projections (provider in `company`,
RotoWire) at

    https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular&position[]=QB

with pts_std / pts_half_ppr / pts_ppr per player-week. Sleeper's player list
(https://api.sleeper.app/v1/players/nfl) maps its ids to gsis ids, which key
the nflverse actuals (data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz).

Writes a gzip CSV, one row per player-week with a projection:
    season, week, sleeper_id, gsis_id, name, pos, team, opponent, company,
    updated_at, pts_std, pts_half_ppr, pts_ppr
plus a JSON sidecar of coverage per season and week (rows, missing weeks,
HTTP errors), so availability is a recorded fact.

The build container cannot reach api.sleeper.app (proxy policy); this runs in
GitHub Actions (.github/workflows/sleeper-projections-backfill.yml) or on
Jeremy's Mac.

Usage:
    python3 pipelines/pull_sleeper_projections.py --seasons 2018-2026 \
        --out data/inputs/weekly_projections_sleeper.csv.gz
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJ = "https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular&position[]={pos}"
PLAYERS = "https://api.sleeper.app/v1/players/nfl"
POSITIONS = ("QB", "RB", "WR", "TE")
FIELDS = ("season", "week", "sleeper_id", "gsis_id", "name", "pos", "team", "opponent", "company",
          "updated_at", "pts_std", "pts_half_ppr", "pts_ppr")
UA = {"User-Agent": "data-driven-football-measurement/1.0"}


def get_json(url: str, tries: int = 4, pause: float = 1.5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:  # noqa: PERF203
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def parse_seasons(text: str) -> list:
    out = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def rows_from(entries: list, season: int, week: int, pos: str, gsis_of: dict) -> list:
    rows = []
    for e in entries or []:
        st = e.get("stats") or {}
        if st.get("pts_ppr") is None:
            continue
        sid = str(e.get("player_id") or "")
        pl = e.get("player") or {}
        name = " ".join(x for x in (pl.get("first_name"), pl.get("last_name")) if x)
        rows.append({"season": season, "week": week, "sleeper_id": sid, "gsis_id": gsis_of.get(sid) or "",
                     "name": name, "pos": pl.get("position") or pos, "team": e.get("team") or "",
                     "opponent": e.get("opponent") or "", "company": e.get("company") or "",
                     "updated_at": e.get("updated_at") or "",
                     "pts_std": st.get("pts_std"), "pts_half_ppr": st.get("pts_half_ppr"),
                     "pts_ppr": st.get("pts_ppr")})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="2018-2026")
    ap.add_argument("--weeks", default="1-18")
    ap.add_argument("--out", type=Path, default=Path("data/inputs/weekly_projections_sleeper.csv.gz"))
    ap.add_argument("--coverage", type=Path, default=None)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args(argv)
    seasons, weeks = parse_seasons(args.seasons), parse_seasons(args.weeks)
    players = get_json(PLAYERS)
    gsis_of = {sid: (p.get("gsis_id") or "").strip() for sid, p in players.items() if isinstance(p, dict)}
    all_rows, coverage = [], {"source": "api.sleeper.app projections (weekly, regular season)",
                              "players_with_gsis": sum(1 for v in gsis_of.values() if v), "seasons": {}}
    for season in seasons:
        cov = coverage["seasons"][str(season)] = {"weeks": {}, "errors": []}
        for week in weeks:
            n = 0
            for pos in POSITIONS:
                try:
                    data = get_json(PROJ.format(season=season, week=week, pos=pos))
                except RuntimeError as e:
                    cov["errors"].append(str(e)[:200])
                    continue
                rows = rows_from(data, season, week, pos, gsis_of)
                all_rows.extend(rows)
                n += len(rows)
                time.sleep(args.sleep)
            cov["weeks"][str(week)] = n
        print(f"{season}: {sum(cov['weeks'].values())} rows, weeks with data "
              f"{[int(w) for w, c in cov['weeks'].items() if c]}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    for r in sorted(all_rows, key=lambda r: (r["season"], r["week"], r["pos"], r["sleeper_id"])):
        w.writerow(r)
    with gzip.open(args.out, "wt", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    cov_path = args.coverage or args.out.with_name(args.out.name.replace(".csv.gz", "") + ".coverage.json")
    coverage["rows"] = len(all_rows)
    coverage["with_gsis"] = sum(1 for r in all_rows if r["gsis_id"])
    cov_path.write_text(json.dumps(coverage, indent=1), encoding="utf-8")
    print(f"wrote {len(all_rows)} rows to {args.out} ({coverage['with_gsis']} with a gsis id); coverage {cov_path}")
    return 0 if all_rows else 1


if __name__ == "__main__":
    sys.exit(main())
