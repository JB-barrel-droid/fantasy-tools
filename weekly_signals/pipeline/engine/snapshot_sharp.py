"""Projection snapshots: sharp-market (pinnacle_implied) + DFS salary-implied (dfs_implied).

pinnacle_implied
----------------
Pinnacle was verified 2026-09-11 to return player props on the Odds API free
tier (probe: 1 market x 1 region = 1 credit; bookmakers add no cost, so
Pinnacle rides the normal odds pull via collectors/odds_api.py BOOKMAKERS).
Per-player implied points come from Pinnacle props ONLY, using the same math
as vegas_implied (engine/vegas.py): the Pinnacle line is the line (no median
needed with one book); anytime-TD fair probability uses Pinnacle's own hold
estimated from its two-sided markets, then Poisson E[TDs] = -ln(1-p).
Coverage gate mirrors v4: players with TD props but no yardage line markets
posted get no number ("no TD-only ghosts").

dfs_implied
-----------
DK salary -> implied PPR points via a per-position $/point flat prior
(SALARY_PER_POINT below). No calibration history exists yet: the Week 1 main
slate excludes the only final game, so salary-vs-actuals overlap is n=1 and
a fitted model would be noise. Rates are anchored to typical DK slate
pricing and are printed every run; refit per position once actuals
accumulate. Half-PPR/standard are derived from expected receptions
(position-average, scaled by the player's salary vs the slate's position
mean) — DK is a full-PPR salary scale, so this is the honest conversion.

Row grain: one row per (batch_id, player_id, game_id, source, scoring_format),
same as snapshot_v4. Batch ids are deterministic per (source, season, week,
vintage) and writes are delete-then-insert, so re-runs never duplicate.
The `vegas_rank` column carries the SOURCE's own positional rank by full-PPR
(Pinnacle-ranked for pinnacle_implied, salary-ranked for dfs_implied);
`ecr_rank` rides along from the ECR crosswalk where resolvable.
"""
import math
import os
import sys
import urllib.parse
import uuid
from collections import defaultdict
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import sbclient  # noqa: E402

from engine.vegas import vegas_implied_points, american_to_prob  # noqa: E402
from engine.snapshot import (  # noqa: E402
    load_ecr, load_players, load_week_games, norm, norm_loose,
)
from engine.snapshot_v4 import load_odds_identity  # noqa: E402
from v4.compute_v4 import LINE_MARKETS  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE")
FMT_MAP = (("std", "standard"), ("half", "half_ppr"), ("ppr", "full_ppr"))

VINTAGE_PIN = "sharp-v1: Pinnacle props only (own hold, Poisson TD)"
VINTAGE_DFS = "dfs-v1: DK salary-implied (flat $/pt prior, rec-scaled)"

# Odds-feed nicknames that don't match players.full_name (same class of fix
# as the fantasypros loader's alias list; keyed on norm_loose form).
NAME_ALIASES = {"kenny gainwell": "kenneth gainwell"}


def alias(name):
    nl = norm_loose(name)
    return NAME_ALIASES.get(nl, nl)

# ------------------------------------------------------------------ priors
# FLAT PRIOR, documented 2026-09-11. Implied full-PPR points = salary / RATE.
# Anchors from typical DK main-slate pricing:
#   $7000 QB ~ 20 pts | $8000 RB ~ 19 | $7800 WR ~ 18 | $6900 TE ~ 16
#   $5000 QB ~ 14     | $5000 RB ~ 12 | $4500 WR ~ 10 | $3500 TE ~ 8
SALARY_PER_POINT = {"QB": 350.0, "RB": 425.0, "WR": 440.0, "TE": 430.0}
# Position-average receptions per game (prior for half/standard derivation).
AVG_REC = {"QB": 0.2, "RB": 3.2, "WR": 4.3, "TE": 3.6}


def batch_id_for(source, season, week, vintage_tag):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                           f"football-signal:sharp:{source}:{season}:w{week}:{vintage_tag}"))


# ------------------------------------------------------- pinnacle props
def load_pinnacle_props():
    """Latest Pinnacle row per (player, market, selection) -> same
    {player: {market: entry}} shape as v4's load_props, Pinnacle only."""
    col = urllib.parse.quote("metadata->>bookmaker", safe="")
    rows = sbclient.get_all(
        "odds_history",
        f"?{col}=eq.pinnacle&select=sportsbook_id,game_id,market,selection,"
        "line,odds,recorded_at,metadata&limit=100000",
    )
    latest = {}
    for r in rows:
        m = r.get("metadata") or {}
        key = (m.get("player_name") or "", r["market"], r["selection"])
        if key not in latest or (r.get("recorded_at") or "") > (
                latest[key].get("recorded_at") or ""):
            latest[key] = r

    per_pm = defaultdict(dict)  # (player, market) -> {"over":..,"under":..,"line":..,"yes":..}
    for (player, market, sel), r in latest.items():
        d = per_pm[(player, market)]
        if market == "player_anytime_td":
            d["yes" if sel == "Yes" else "no"] = r["odds"]
        else:
            if sel == "Over":
                d["over"], d["line"] = r["odds"], r["line"]
            else:
                d["under"] = r["odds"]
                d.setdefault("line", r["line"])

    # Pinnacle's own hold from its two-sided markets (No side of TD never posted)
    holds = []
    for (player, market), o in per_pm.items():
        if market == "player_anytime_td":
            continue
        if o.get("over") is not None and o.get("under") is not None:
            try:
                holds.append(american_to_prob(o["over"])
                             + american_to_prob(o["under"]) - 1.0)
            except ValueError:
                pass
    holds.sort()
    hold = holds[len(holds) // 2] if holds else 0.05

    player_props = {}
    for (player, market), o in per_pm.items():
        if market == "player_anytime_td":
            if "yes" not in o:
                continue
            try:
                p_yes = american_to_prob(o["yes"])
            except ValueError:
                continue
            fair = max(0.01, min(0.99, p_yes - hold / 2))
            etd = -math.log(1 - fair) if fair < 1 else 3.0
            player_props.setdefault(player, {})[market] = {"prob": etd}
        else:
            if o.get("line") is None:
                continue
            entry = {"line": o["line"]}
            if o.get("over") is not None and o.get("under") is not None:
                entry["over_odds"], entry["under_odds"] = o["over"], o["under"]
            player_props.setdefault(player, {})[market] = entry
    return player_props


# ------------------------------------------------------- dfs implied
def load_dfs_salaries(season, week):
    rows = sbclient.get_all(
        "dfs_salaries",
        f"?season=eq.{season}&week=eq.{week}"
        "&select=player_id,player_name,position,team,salary&limit=10000",
    )
    return [r for r in rows
            if r.get("player_id") and r.get("position") in POSITIONS
            and r.get("salary")]


def dfs_points(season, week):
    """{player_id: {'ppr','half','std', 'pos', 'name', 'salary'}}."""
    rows = load_dfs_salaries(season, week)
    mean_sal = {}
    for pos in POSITIONS:
        ss = [r["salary"] for r in rows if r["position"] == pos]
        mean_sal[pos] = sum(ss) / len(ss) if ss else 1.0
    out = {}
    for r in rows:
        pos = r["position"]
        sal = float(r["salary"])
        ppr = round(sal / SALARY_PER_POINT[pos], 2)
        exp_rec = AVG_REC[pos] * sal / mean_sal[pos]
        out[r["player_id"]] = {
            "ppr": ppr,
            "half": round(ppr - 0.5 * exp_rec, 2),
            "std": round(ppr - exp_rec, 2),
            "pos": pos, "name": r["player_name"], "salary": sal,
        }
    return out


# ------------------------------------------------------- build + write
def _ecr_by_pid(by_name, by_loose, ecr):
    out = {}
    for nm, info in ecr.items():
        if info.get("pos_rank") is None:
            continue
        pl = by_name.get(nm) or by_loose.get(norm_loose(nm))
        if pl:
            out.setdefault(pl["id"], info["pos_rank"])
    return out


def build_rows(batch_pin, batch_dfs, season=2026, week=1):
    player_props = load_pinnacle_props()
    dfsp = dfs_points(season, week)
    ecr = load_ecr()
    by_name, by_loose, by_id = load_players()
    games_by_id, games_by_team = load_week_games(season, week)
    uuid_by_name, game_by_name = load_odds_identity()
    ecr_by_pid = _ecr_by_pid(by_name, by_loose, ecr)
    snap_at = datetime.now(timezone.utc).isoformat()

    rows, gaps = [], {"pin_no_uuid": [], "pin_no_game": [], "pin_td_only": [],
                      "dfs_no_game": []}

    # --- pinnacle_implied ---
    rank_src = defaultdict(list)
    tmp = []
    for raw_name in sorted(player_props):
        props = player_props[raw_name]
        if not (set(props.keys()) & LINE_MARKETS):
            gaps["pin_td_only"].append(raw_name)
            continue
        pid = uuid_by_name.get(raw_name)
        if not pid:
            fb = by_loose.get(alias(raw_name))
            pid = fb["id"] if fb else None
        if not pid:
            gaps["pin_no_uuid"].append(raw_name)
            continue
        pl = by_id.get(pid)
        pos = (ecr.get(norm(raw_name)) or {}).get("pos") or \
            (pl.get("position") if pl else None)
        if pos not in POSITIONS:
            continue
        gid = game_by_name.get(raw_name)
        if not gid or gid not in games_by_id:
            g = games_by_team.get(pl.get("team_id")) if pl else None
            gid = g["id"] if g else None
        if not gid:
            gaps["pin_no_game"].append(raw_name)
            continue
        try:
            raw = {sc: vegas_implied_points(props, position=pos, scoring=sc)["points"]
                   for sc in ("standard", "half_ppr", "ppr")}
        except Exception:
            continue
        pts = {"std": raw["standard"], "half": raw["half_ppr"], "ppr": raw["ppr"]}
        rank_src[pos].append((pts["ppr"], pid))
        tmp.append((pid, gid, raw_name, pts, pos))

    rank_of = {}
    for pos, lst in rank_src.items():
        for i, (_, pid) in enumerate(sorted(lst, reverse=True), 1):
            rank_of[pid] = i
    for pid, gid, raw_name, pts, pos in tmp:
        for fkey, fmt in FMT_MAP:
            rows.append({
                "batch_id": batch_pin, "player_id": pid, "game_id": gid,
                "season": season, "week": week, "source": "pinnacle_implied",
                "scoring_format": fmt, "projected_points": pts[fkey],
                "ecr_rank": ecr_by_pid.get(
                    pid, (ecr.get(norm(raw_name)) or {}).get("pos_rank")),
                "vegas_rank": rank_of.get(pid),
                "snapshot_at": snap_at, "vintage_note": VINTAGE_PIN,
            })

    # --- dfs_implied ---
    rank_dfs = defaultdict(list)
    tmp_dfs = []
    for pid, d in dfsp.items():
        pl = by_id.get(pid)
        g = games_by_team.get(pl.get("team_id")) if pl else None
        if not g:
            gaps["dfs_no_game"].append(d["name"])
            continue
        rank_dfs[d["pos"]].append((d["ppr"], pid))
        tmp_dfs.append((pid, g["id"], d))
    rank_of_dfs = {}
    for pos, lst in rank_dfs.items():
        for i, (_, pid) in enumerate(sorted(lst, reverse=True), 1):
            rank_of_dfs[pid] = i
    for pid, gid, d in tmp_dfs:
        for fkey, fmt in FMT_MAP:
            rows.append({
                "batch_id": batch_dfs, "player_id": pid, "game_id": gid,
                "season": season, "week": week, "source": "dfs_implied",
                "scoring_format": fmt, "projected_points": d[fkey],
                "ecr_rank": ecr_by_pid.get(pid),
                "vegas_rank": rank_of_dfs.get(pid),
                "snapshot_at": snap_at, "vintage_note": VINTAGE_DFS,
            })
    return rows, gaps


def write_batch(rows, batch_id, source):
    """Idempotent: delete any prior rows for this deterministic batch, then insert."""
    sbclient.delete("projection_snapshots", f"?batch_id=eq.{batch_id}")
    mine = [r for r in rows if r["batch_id"] == batch_id]
    for i in range(0, len(mine), 200):
        sbclient.post("projection_snapshots", mine[i:i + 200])
    return len(mine)


def main(season=2026, week=1):
    batch_pin = batch_id_for("pinnacle_implied", season, week, "v1")
    batch_dfs = batch_id_for("dfs_implied", season, week, "v1")
    rows, gaps = build_rows(batch_pin, batch_dfs, season=season, week=week)
    n_pin = write_batch(rows, batch_pin, "pinnacle_implied")
    n_dfs = write_batch(rows, batch_dfs, "dfs_implied")
    print(f"pinnacle_implied: {n_pin} rows (batch {batch_pin[:8]}…) "
          f"[{n_pin // 3} players x 3 formats]")
    print(f"dfs_implied: {n_dfs} rows (batch {batch_dfs[:8]}…) "
          f"[{n_dfs // 3} players x 3 formats]")
    print("active DFS $/point prior:", SALARY_PER_POINT)
    for g, names in gaps.items():
        print(f"gap {g}: {len(names)}", names[:6] if names else "")
    return {"pinnacle_implied": n_pin, "dfs_implied": n_dfs}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    main(season=a.season, week=a.week)
