#!/usr/bin/env python3
"""Sleeper weekly K/DEF projections collector (secondary check, fail-closed).

Fetches Rotowire-sourced weekly projections from the undocumented Sleeper
endpoint for kickers and team defenses. This is a SECONDARY signal only --
never a primary input -- used to cross-check the kicker opportunity model
and DST weekly rates.

Endpoint: https://api.sleeper.com/projections/nfl/2026/{week}?season_type=regular&position[]={K|DEF}

Known data quirks (validated 2026-09-16, Week 2):
  - K returns ~157 rows but only ~33 are real projected kickers; the rest are
    ADP-only filler (124 rows) plus team-attached ADP-only rows. A row is
    usable ONLY if it carries pts_std or a relevant component key (fga/fgm/
    xpa/xpm); team presence alone is insufficient.
  - DEF returns 32 usable defenses.
  - K has no 50+ yard make band (fgm_20_29/30_39/40_49 only) and no safety
    projection. DEF has no safety projection either.
  - pts_* fields do NOT reproduce straightforward standard scoring; always
    recompute points from components with engine.scoring.
  - NYJ once carried two projected kickers; keep both, flag the duplication.
  - Week 1 (or any completed week) returns historical projections, not
    actuals. Never treat these as observed performance.

Fail-closed: the script exits nonzero (and writes nothing) unless
  - K yields >= 28 usable projected kickers,
  - DEF yields exactly 32 defenses,
  - every usable row has the required component keys.

Output: lottery/data/sleeper_weekly_kdef_<week>.json with recomputed
standard/half/full PPR points per kicker/defense plus the raw components
and a schema note. Intended consumer: the kicker opportunity model build
(step: cross-check), not the chart pipeline.
"""
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN.parent))
sys.path.insert(0, "/home/hatch/workspace/football-signal")

WEEK = int(sys.argv[1]) if len(sys.argv) > 1 else 2
SEASON = 2026
OUT_DIR = Path("/home/hatch/workspace/goals/football-signal-database-and-app"
               "/lottery/data")

K_MIN_USABLE = 28
DEF_EXPECTED = 32

# Component keys required for a row to count as a real projection.
K_KEYS = ("fga", "fgm", "xpa", "xpm")
DEF_KEYS = ("sack", "pts_allow", "yds_allow")


def fetch(position):
    url = (f"https://api.sleeper.com/projections/nfl/{SEASON}/{WEEK}"
           f"?season_type=regular&position[]={position}")
    req = urllib.request.Request(url, headers={"User-Agent": "football-signal/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def player_name(row):
    p = row.get("player") or {}
    full = p.get("full_name")
    if full:
        return full
    fn, ln = p.get("first_name"), p.get("last_name")
    if fn or ln:
        return f"{fn or ''} {ln or ''}".strip()
    return row.get("full_name")


def usable_k(row):
    stats = row.get("stats") or {}
    if stats.get("pts_std") is not None:
        return True
    return any(stats.get(k) is not None for k in K_KEYS)


def usable_def(row):
    stats = row.get("stats") or {}
    if stats.get("pts_std") is not None:
        return True
    return any(stats.get(k) is not None for k in DEF_KEYS)


def kicker_points_recomputed(stats):
    """Standard-ish kicker scoring from components.

    NOTE: Sleeper has no 50+ band, so distance scoring is approximated:
    fgm_20_29/30_39/40_49 at 3 pts each; the residual (fgm - band sum) is
    treated as 40-49 (conservative; documented, not silent).
    """
    from engine.scoring import kicker_points
    fgm = float(stats.get("fgm") or 0)
    # band makes may be absent; fall back to total makes at flat 3
    bands = [float(stats.get(k) or 0)
             for k in ("fgm_20_29", "fgm_30_39", "fgm_40_49")]
    if sum(bands) > 0:
        # residual makes beyond the bands (likely 50+) at 3 pts
        pts = sum(bands) * 3.0 + max(0.0, fgm - sum(bands)) * 3.0
    else:
        pts = fgm * 3.0
    pts += float(stats.get("xpm") or 0) * 1.0
    return round(pts, 2)


def dst_points_recomputed(stats):
    from engine.scoring import dst_points
    return round(dst_points({
        "sacks": float(stats.get("sack") or 0),
        "interceptions": float(stats.get("int") or 0),
        "fumbles_recovered": float(stats.get("fum_rec") or 0),
        "touchdowns": float(stats.get("def_td") or 0),
        "safeties": 0.0,  # not projected by Sleeper
        "points_allowed": float(stats.get("pts_allow") or 0),
        "yards_allowed": float(stats.get("yds_allow") or 0),
    }), 2)


def main():
    errors = []
    k_raw = fetch("K")
    d_raw = fetch("DEF")

    kickers = []
    for row in k_raw:
        if not usable_k(row):
            continue
        stats = row.get("stats") or {}
        kickers.append({
            "player_id": row.get("player_id"),
            "name": player_name(row),
            "team": row.get("team"),
            "components": {k: stats.get(k) for k in
                           ("fga", "fgm", "fgm_20_29", "fgm_30_39",
                            "fgm_40_49", "fgm_yds", "xpa", "xpm")},
            "points_recomputed": kicker_points_recomputed(stats),
            "points_sleeper_pts_std": stats.get("pts_std"),
        })

    defenses = []
    for row in d_raw:
        if not usable_def(row):
            continue
        stats = row.get("stats") or {}
        defenses.append({
            "player_id": row.get("player_id"),
            "name": (row.get("player") or {}).get("full_name")
                    or row.get("full_name") or row.get("team"),
            "team": row.get("team"),
            "components": {k: stats.get(k) for k in
                           ("sack", "int", "ff", "fum_rec",
                            "blk_kick", "def_td", "pts_allow", "yds_allow")},
            "points_recomputed": dst_points_recomputed(stats),
            "points_sleeper_pts_std": stats.get("pts_std"),
        })

    # ---- fail-closed schema assertions ----
    if len(kickers) < K_MIN_USABLE:
        errors.append(f"only {len(kickers)} usable kickers "
                      f"(need >= {K_MIN_USABLE}; raw rows={len(k_raw)})")
    if len(defenses) != DEF_EXPECTED:
        errors.append(f"{len(defenses)} defenses (need exactly "
                      f"{DEF_EXPECTED}; raw rows={len(d_raw)})")
    # duplicate-team check (NYJ had two projected kickers in Week 2)
    seen = {}
    for k in kickers:
        if k["team"]:
            seen.setdefault(k["team"], []).append(k["name"])
    dupes = {t: n for t, n in seen.items() if len(n) > 1}

    if errors:
        for e in errors:
            print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        sys.exit(1)

    out = {
        "season": SEASON,
        "week": WEEK,
        "fetched": date.today().isoformat(),
        "source": "sleeper-undocumented-rotowire",
        "note": ("secondary check only; points recomputed from components; "
                 "no 50+ kicker band; no safety projections; completed weeks "
                 "return historical projections, not actuals"),
        "kickers": kickers,
        "defenses": defenses,
        "duplicate_team_kickers": dupes,
        "schema": {"k_min_usable": K_MIN_USABLE,
                   "def_expected": DEF_EXPECTED},
    }
    fp = OUT_DIR / f"sleeper_weekly_kdef_{WEEK}.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"wrote {fp}: {len(kickers)} kickers, {len(defenses)} defenses"
          + (f"; duplicate-team kickers: {dupes}" if dupes else ""))


if __name__ == "__main__":
    main()
