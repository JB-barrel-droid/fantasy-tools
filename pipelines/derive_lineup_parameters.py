#!/usr/bin/env python3
"""Derive the expected-starts parameters from the project's own data (JEG-521 G2, G3).

The expected-starts value (docs/methodology.md "Expected-starts value", ES-*)
needs, per position:

  m_pos        the per-game missed-game hazard of a healthy rostered player
               (injury, benching, rest) over the rest-of-season window;
  bye share    the fraction of remaining team-weeks that are byes;
  sigma_rel    the relative uncertainty of a player's rest-of-season per-game
               level, with an absolute floor sigma_floor (points per game).

Nothing here is assumed. Every number is measured from files in the repo:

  data/inputs/weekly_actuals_2024_2026.csv   realized fantasy points per
      player-game, 2024, 2025 and 2026 weeks 1-4 (QB/RB/WR/TE). Exported
      2026-10-09 from Supabase public.v_player_game_actuals joined to
      public.games / public.players / public.teams (the SQL is in
      docs/methodology.md ES-A). A row exists when the player recorded a stat
      line; no row in a week his team played is a missed game.
  data/inputs/nfl_schedule_2024_2026.json    the weeks each team plays, per
      season (public.games). The missing week is the bye.
  data/inputs/nfl_byes_2026.json             the 2026 bye table (cross-checked
      against the schedule by tests/test_derive_lineup_parameters.py).
  data/fixtures/current/players.json         this week's per-game projections
      from ESPN, CBS rest of season and Razzball (espn_ppg, cbsros_ppg,
      rz_ppg) and the Sleeper injury status.
  data/history/week-N.json                   the per-game projections each
      source served in earlier content weeks.

Estimators
----------
m_pos (G3). For each past season and each selection window W_sel = weeks
1..k, rank players at a position by mean points per game over W_sel (at least
MIN_GAMES games), keeping only players who played their team's last game in
W_sel ("healthy at valuation"; a player already out is priced by the
projections, not by m). The top S_p are the starters and the next b_p the
bench, where S_p / b_p are the 12-team allocation counts (ES-2). Over the
measurement window weeks k+1..17 (week 18 is excluded: starters rest), a team
game with no stat line is a missed game. m_pos = missed / team games, pooled
over seasons and windows, with a normal-approximation 95% interval. The
split into temporary (he played again later) and season-ending absences is
reported. Selecting on the past and measuring on the future avoids survivor
bias (a season-total ranking only picks players who stayed healthy).

Bye share. Over the rest-of-season window (content week + 1 .. 18), the
fraction of team-weeks that are byes, league-wide: 30 of 32 teams have a bye
after week 5 in 2026, so 30 / (32 x 13).

sigma (G2). Two estimates, documented as stand-ins until realized projection
error can be measured (G4):
  (a) cross-source spread: for every healthy player at least two of ESPN, CBS
      rest of season and Razzball project, the sample standard deviation of
      the three per-game projections over their mean, at the league's
      scoring. Reported by level bucket. sigma_rel is the median over the
      players ranked between S_p / 2 and N_p (the band the start-worthy
      question is about); sigma_floor is the median absolute spread below
      the starter count (deep players, where a relative sigma vanishes).
  (b) week-to-week movement: for each projection source and consecutive pair
      of content weeks in data/history, the relative change of each player's
      per-game projection, demeaned by the position median (ESPN's history
      carries a known level shift, GAP-GAMES-REMAINING-STALE), robust scale
      1.4826 x MAD. That is one week's drift of the level; the drift over the
      remaining window grows with the square root of the weeks left to
      resolve, reported at h = weeks remaining / 2.
  Also reported, for context only: the realized weekly noise of starters
  (standard deviation of weekly points over their mean, 2024-2025), which is
  what a manager faces when setting a lineup and is much larger than either
  sigma above.

Usage
-----
    python3 pipelines/derive_lineup_parameters.py [--out output/lineup-parameters.json]
        [--report output/lineup-parameters.md] [--teams 12] [--scoring ppr]
        [--content-week N]

Exit 0 always; this is analysis, not a gate.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
SCHEDULE = REPO / "data" / "inputs" / "nfl_schedule_2024_2026.json"
BYES = REPO / "data" / "inputs" / "nfl_byes_2026.json"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
HISTORY = REPO / "data" / "history"
OUT = REPO / "output" / "lineup-parameters.json"
REPORT = REPO / "output" / "lineup-parameters.md"
CONFIG = REPO / "config" / "lineup_parameters.json"
SCHEMA = "lineup-parameters/1"

POSITIONS = ("QB", "RB", "WR", "TE")
SCORINGS = ("standard", "half_ppr", "ppr")
PPG_FIELDS = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
# Sleeper statuses that mean the player is not available this week.
UNAVAILABLE = frozenset({"Out", "IR", "Doubtful", "PUP", "Sus", "NA", "DNR"})
# Roster constants (docs/methodology.md VP-0 / VP-2.2). WR 3 / FLEX 1 is the
# engine's default roster; the JEG-521 spec settles the config mismatch on it.
DEDICATED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
FLEX = 1
BENCH = 6
BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
MIN_GAMES = 3
LAST_MEASURED_WEEK = 17  # week 18: contenders rest starters
SELECTION_WINDOWS = ((1, 5), (1, 9))
SEASONS = (2024, 2025)
MAD_TO_SD = 1.4826
MIN_PPG_FOR_MOVEMENT = 5.0


# --------------------------------------------------------------------------- roster


def dhondt(seats: int, weights: dict, order=POSITIONS) -> dict:
    alloc = {p: 0 for p in weights}
    for _ in range(max(0, seats)):
        best, best_q = None, -1.0
        for p in order:
            if p not in weights:
                continue
            q = weights[p] / (alloc[p] + 1)
            if q > best_q + 1e-15:
                best, best_q = p, q
        alloc[best] += 1
    return alloc


def pool_sizes(teams: int) -> dict:
    """Starter and rostered counts per position at `teams` on the default
    roster. The flex slots are split evenly between RB and WR here (the live
    engine fills them by each source's own values, VP-2.2c; for a historical
    pool the even split is the neutral choice and is reported)."""
    bench = dhondt(round(teams * BENCH), dict(BENCH_MIX_12))
    starters = {p: teams * DEDICATED[p] for p in POSITIONS}
    flex = teams * FLEX
    starters["RB"] += flex // 2
    starters["WR"] += flex - flex // 2
    return {p: {"starters": starters[p], "bench": bench[p], "rostered": starters[p] + bench[p]}
            for p in POSITIONS}


# --------------------------------------------------------------------------- inputs


def load_actuals(path=ACTUALS) -> list:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        out.append({"season": int(r["season"]), "week": int(r["week"]), "player_key": int(r["player_key"]),
                    "pos": r["pos"], "team": r["team"],
                    "pts": {"standard": float(r["std"]), "half_ppr": float(r["half_ppr"]), "ppr": float(r["ppr"])}})
    return out


def load_schedule(path=SCHEDULE) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {int(season): {team: [int(w) for w in weeks] for team, weeks in teams.items()}
            for season, teams in doc["seasons"].items()}


def load_history(root=HISTORY) -> dict:
    """{week: {source: {player_key: [std, half, ppr]}}} for the projection sources."""
    docs = {}
    for path in sorted(Path(root).glob("week-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        week = int(doc["week"])
        docs[week] = {k: v["ppg"] for k, v in doc["sources"].items() if v.get("kind") == "projection"}
    return docs


# --------------------------------------------------------------------------- m_pos


def _player_weeks(actuals, season, lo, hi, scoring):
    pts = defaultdict(dict)
    teams = defaultdict(Counter)
    for r in actuals:
        if r["season"] == season and lo <= r["week"] <= hi:
            key = (r["player_key"], r["pos"])
            pts[key][r["week"]] = r["pts"][scoring]
            teams[key][r["team"]] += 1
    return pts, teams


def missed_game_rates(actuals, schedule, season, select_window, measure_window, sizes,
                      scoring="ppr", healthy_at_valuation=True, min_games=MIN_GAMES) -> dict:
    """Per position: {starters|bench|rostered: {missed, games, temporary, season_ending, players}}.

    Selection: rank by mean points per game over select_window (>= min_games
    games); with healthy_at_valuation, the player must have played his team's
    last game inside the selection window. Measurement: over measure_window,
    each team game with no stat line is a missed game."""
    s_lo, s_hi = select_window
    m_lo, m_hi = measure_window
    sel, sel_teams = _player_weeks(actuals, season, s_lo, s_hi, scoring)
    meas, _ = _player_weeks(actuals, season, m_lo, m_hi, scoring)
    sched = schedule[season]
    out = {}
    for pos in POSITIONS:
        cands = []
        for key, weeks in sel.items():
            if key[1] != pos or len(weeks) < min_games:
                continue
            team = sel_teams[key].most_common(1)[0][0]
            if team not in sched:
                continue
            if healthy_at_valuation:
                team_weeks = [w for w in sched[team] if w <= s_hi]
                if not team_weeks or team_weeks[-1] not in weeks:
                    continue
            cands.append((key, team, statistics.mean(weeks.values())))
        cands.sort(key=lambda c: (-c[2], c[0][0]))
        n_s, n_b = sizes[pos]["starters"], sizes[pos]["bench"]
        groups = {"starters": cands[:n_s], "bench": cands[n_s:n_s + n_b], "rostered": cands[:n_s + n_b]}
        res = {}
        for name, group in groups.items():
            missed = games = temporary = season_ending = 0
            for key, team, _ in group:
                team_games = [w for w in sched[team] if m_lo <= w <= m_hi]
                played = [w for w in team_games if w in meas.get(key, {})]
                miss = [w for w in team_games if w not in meas.get(key, {})]
                games += len(team_games)
                missed += len(miss)
                if miss:
                    if played and max(played) > max(miss):
                        temporary += len(miss)
                    else:
                        season_ending += len(miss)
            res[name] = {"missed": missed, "games": games, "temporary": temporary,
                         "season_ending": season_ending, "players": len(group),
                         "rate": (missed / games) if games else None}
        out[pos] = res
    return out


def pooled_rates(actuals, schedule, sizes, seasons=SEASONS, windows=SELECTION_WINDOWS,
                 last_week=LAST_MEASURED_WEEK, scoring="ppr") -> dict:
    """m_pos pooled over seasons and selection windows, per group, with a
    normal-approximation 95% interval and the per-cell detail."""
    cells = []
    acc = {pos: {g: Counter() for g in ("starters", "bench", "rostered")} for pos in POSITIONS}
    for season in seasons:
        if season not in schedule:
            continue
        for lo, hi in windows:
            r = missed_game_rates(actuals, schedule, season, (lo, hi), (hi + 1, last_week), sizes, scoring)
            cells.append({"season": season, "select": [lo, hi], "measure": [hi + 1, last_week],
                          "rates": {pos: {g: r[pos][g]["rate"] for g in r[pos]} for pos in POSITIONS}})
            for pos in POSITIONS:
                for g in acc[pos]:
                    for k in ("missed", "games", "temporary", "season_ending"):
                        acc[pos][g][k] += r[pos][g][k]
    pooled = {}
    for pos in POSITIONS:
        pooled[pos] = {}
        for g, c in acc[pos].items():
            n = c["games"]
            m = c["missed"] / n if n else None
            half = 1.96 * math.sqrt(m * (1 - m) / n) if n and m is not None else None
            pooled[pos][g] = {"rate": m, "games": n, "missed": c["missed"],
                              "temporary_rate": (c["temporary"] / n) if n else None,
                              "season_ending_rate": (c["season_ending"] / n) if n else None,
                              "ci95": [max(0.0, m - half), min(1.0, m + half)] if half is not None else None}
    return {"pooled": pooled, "cells": cells}


def bye_share(byes: dict, first_week: int, last_week: int) -> dict:
    """League-wide share of team-weeks in [first_week, last_week] that are byes."""
    weeks = last_week - first_week + 1
    teams_with_bye = sum(1 for w in byes.values() if first_week <= w <= last_week)
    return {"first_week": first_week, "last_week": last_week, "weeks": weeks,
            "teams_with_bye_in_window": teams_with_bye, "teams": len(byes),
            "share": (teams_with_bye / (len(byes) * weeks)) if weeks > 0 and byes else 0.0}


# --------------------------------------------------------------------------- sigma


def _sample_sd(values):
    if len(values) < 2:
        return None
    return statistics.stdev(values)


def cross_source_sigma(players: list, sizes: dict, scoring="ppr") -> dict:
    """Relative spread of the per-game projections across sources, per position.

    Players with an unavailable Sleeper status are excluded (ESPN's per-game
    number for them is per team game, so their spread is absence, not
    disagreement). Buckets are by rank on the mean projection."""
    out = {}
    for pos in POSITIONS:
        rows = []
        for p in players:
            if p.get("pos") != pos:
                continue
            vals = [p.get(f, {}).get(scoring) for f in PPG_FIELDS.values()]
            vals = [v for v in vals if isinstance(v, (int, float)) and v > 0]
            if len(vals) < 2:
                continue
            mean = statistics.mean(vals)
            sd = _sample_sd(vals)
            rows.append({"key": p.get("player_key"), "mean": mean, "sd": sd, "rel": sd / mean,
                         "unavailable": p.get("injury_status") in UNAVAILABLE})
        rows.sort(key=lambda r: -r["mean"])
        healthy = [r for r in rows if not r["unavailable"]]
        n_s, n_r = sizes[pos]["starters"], sizes[pos]["rostered"]
        buckets = []
        edges = [(0, n_s // 2, "top half of starters"), (n_s // 2, n_s, "lower half of starters"),
                 (n_s, n_r, "bench"), (n_r, len(healthy), "below the roster")]
        for lo, hi, label in edges:
            seg = healthy[lo:hi]
            if not seg:
                continue
            buckets.append({"label": label, "ranks": [lo + 1, hi], "players": len(seg),
                            "median_rel": statistics.median(r["rel"] for r in seg),
                            "mean_rel": statistics.mean(r["rel"] for r in seg),
                            "median_abs_sd": statistics.median(r["sd"] for r in seg),
                            "mean_ppg": statistics.mean(r["mean"] for r in seg)})
        band = healthy[n_s // 2:n_r]
        deep = healthy[n_s:]
        out[pos] = {
            "players_with_two_sources": len(rows), "healthy": len(healthy),
            "buckets": buckets,
            "sigma_rel": statistics.median(r["rel"] for r in band) if band else None,
            "sigma_floor": statistics.median(r["sd"] for r in deep) if deep else None,
            "unavailable_median_rel": (statistics.median(r["rel"] for r in rows if r["unavailable"])
                                       if any(r["unavailable"] for r in rows) else None),
        }
    return out


def week_to_week_sigma(history: dict, pos_of: dict, scoring_index=2, min_ppg=MIN_PPG_FOR_MOVEMENT) -> dict:
    """Robust relative weekly movement of each source's per-game projection,
    demeaned by the position median of that pair of weeks. {source: {pos: {...}}}"""
    out = defaultdict(dict)
    weeks = sorted(history)
    for a, b in zip(weeks, weeks[1:]):
        for src in PPG_FIELDS:
            if src not in history[a] or src not in history[b]:
                continue
            A, B = history[a][src], history[b][src]
            rel = defaultdict(list)
            for key, va in A.items():
                vb = B.get(key)
                if vb is None:
                    continue
                x, y = va[scoring_index], vb[scoring_index]
                if x >= min_ppg and y > 0:
                    rel[pos_of.get(int(key))].append((y - x) / x)
            for pos in POSITIONS:
                r = rel.get(pos) or []
                if len(r) < 5:
                    continue
                med = statistics.median(r)
                mad = statistics.median(abs(v - med) for v in r)
                out[src].setdefault(pos, []).append({"weeks": [a, b], "players": len(r), "median_shift": med,
                                                     "robust_sd": MAD_TO_SD * mad})
    return dict(out)


def summarize_movement(movement: dict, horizon_weeks: float) -> dict:
    """Per position: the mean weekly robust sd across sources and week pairs,
    and the same scaled to half the remaining window (random-walk drift)."""
    out = {}
    for pos in POSITIONS:
        vals = [c["robust_sd"] for src in movement.values() for c in src.get(pos, [])]
        if not vals:
            out[pos] = None
            continue
        weekly = statistics.mean(vals)
        out[pos] = {"weekly_rel_sd": weekly, "cells": len(vals),
                    "horizon_weeks": horizon_weeks,
                    "horizon_rel_sd": weekly * math.sqrt(max(horizon_weeks, 0.0))}
    return out


def weekly_noise(actuals, schedule, sizes, seasons=SEASONS, scoring="ppr") -> dict:
    """Realized weekly noise of starters: median over players of sd / mean of
    weekly points (weeks 1-17, >= 6 games), per position."""
    out = {}
    for pos in POSITIONS:
        cvs = []
        for season in seasons:
            pts, _ = _player_weeks(actuals, season, 1, LAST_MEASURED_WEEK, scoring)
            cands = sorted(((k, v) for k, v in pts.items() if k[1] == pos and len(v) >= 6),
                           key=lambda kv: -statistics.mean(kv[1].values()))[:sizes[pos]["starters"]]
            for _, v in cands:
                vals = list(v.values())
                mean = statistics.mean(vals)
                if mean > 0:
                    cvs.append(statistics.stdev(vals) / mean)
        out[pos] = {"median_cv": statistics.median(cvs) if cvs else None, "players": len(cvs)}
    return out


# --------------------------------------------------------------------------- recommend


def recommend(m: dict, cross: dict, movement_summary: dict, byes: dict) -> dict:
    """The parameters the spec uses, each with its source named."""
    rec = {}
    for pos in POSITIONS:
        starters = m["pooled"][pos]["starters"]
        rostered = m["pooled"][pos]["rostered"]
        cs = cross[pos]
        mv = movement_summary.get(pos) or {}
        rec[pos] = {
            "m": starters["rate"],
            "m_source": "healthy starters, 2024-2025, selection weeks 1-5 and 1-9, measured to week 17",
            "m_ci95": starters["ci95"],
            "m_rostered": rostered["rate"],
            "sigma_rel_now": cs["sigma_rel"],
            "sigma_rel_drift": mv.get("horizon_rel_sd"),
            "sigma_rel": (math.sqrt((cs["sigma_rel"] or 0) ** 2 + (mv.get("horizon_rel_sd") or 0) ** 2)
                          if cs["sigma_rel"] is not None else None),
            "sigma_rel_source": "sqrt(cross-source spread^2 + weekly drift^2 x half the remaining weeks)",
            "sigma_floor": cs["sigma_floor"],
            "sigma_floor_source": "median absolute spread across sources below the starter count",
        }
    rec["bye_share"] = byes["share"]
    return rec


# --------------------------------------------------------------------------- report


def _pct(x, d=1):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def render_report(doc: dict) -> str:
    rec = doc["recommended"]
    L = []
    L.append("# Expected-starts parameters, derived from repo data")
    L.append("")
    L.append(f"Content week {doc['content_week']}, {doc['scoring']} scoring, {doc['teams']} teams. "
             f"Schema `{doc['schema']}`. Produced by `pipelines/derive_lineup_parameters.py`.")
    L.append("")
    L.append("## Recommended parameters")
    L.append("")
    L.append("| Position | m (healthy starters) | 95% interval | m, all rostered | sigma now (spread) "
             "| sigma drift (to mid-window) | sigma used | sigma floor (ppg) |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for pos in POSITIONS:
        r = rec[pos]
        ci = r["m_ci95"]
        L.append(f"| {pos} | {_pct(r['m'])} | {_pct(ci[0])} to {_pct(ci[1])} | {_pct(r['m_rostered'])} | "
                 f"{_pct(r['sigma_rel_now'])} | {_pct(r['sigma_rel_drift'])} | {_pct(r['sigma_rel'])} | "
                 f"{r['sigma_floor']:.2f} |")
    b = doc["bye_share"]
    L.append("")
    L.append(f"Bye share of remaining team-weeks: {_pct(b['share'])} "
             f"({b['teams_with_bye_in_window']} of {b['teams']} teams have a bye in weeks "
             f"{b['first_week']}-{b['last_week']}, {b['weeks']} weeks).")
    L.append("")
    L.append("## Missed-game hazard by cell (rate of team games with no stat line)")
    L.append("")
    L.append("| Season | Selected on | Measured | QB starters | RB starters | WR starters | TE starters "
             "| QB rostered | RB rostered | WR rostered | TE rostered |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for c in doc["missed_games"]["cells"]:
        s = c["rates"]
        L.append(f"| {c['season']} | weeks {c['select'][0]}-{c['select'][1]} | weeks {c['measure'][0]}-{c['measure'][1]} | "
                 + " | ".join(_pct(s[p]["starters"]) for p in POSITIONS) + " | "
                 + " | ".join(_pct(s[p]["rostered"]) for p in POSITIONS) + " |")
    L.append("")
    L.append("Pooled, with the split into temporary absences (the player returned) and season-ending ones:")
    L.append("")
    L.append("| Position | Group | Team games | Missed | Rate | Temporary | Season-ending |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for pos in POSITIONS:
        for g in ("starters", "bench", "rostered"):
            c = doc["missed_games"]["pooled"][pos][g]
            L.append(f"| {pos} | {g} | {c['games']} | {c['missed']} | {_pct(c['rate'])} | "
                     f"{_pct(c['temporary_rate'])} | {_pct(c['season_ending_rate'])} |")
    L.append("")
    L.append("## Cross-source spread this week (sample sd over mean of ESPN, CBS rest of season, Razzball)")
    L.append("")
    L.append("| Position | Bucket | Ranks | Players | Median relative | Mean relative | Median absolute (ppg) | Mean ppg |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for pos in POSITIONS:
        for bkt in doc["cross_source"][pos]["buckets"]:
            L.append(f"| {pos} | {bkt['label']} | {bkt['ranks'][0]}-{bkt['ranks'][1]} | {bkt['players']} | "
                     f"{_pct(bkt['median_rel'])} | {_pct(bkt['mean_rel'])} | {bkt['median_abs_sd']:.2f} | "
                     f"{bkt['mean_ppg']:.1f} |")
    L.append("")
    L.append("Players with an unavailable Sleeper status are excluded above. Their median relative spread: "
             + ", ".join(f"{pos} {_pct(doc['cross_source'][pos]['unavailable_median_rel'])}" for pos in POSITIONS)
             + ". That spread is absence (ESPN's per-game number is per team game), not disagreement.")
    L.append("")
    L.append("## Week-to-week movement of the per-game projections (relative, demeaned, robust sd)")
    L.append("")
    L.append("| Source | Weeks | Position | Players | Median shift | Robust sd |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for src, by_pos in doc["week_to_week"].items():
        for pos in POSITIONS:
            for c in by_pos.get(pos, []):
                L.append(f"| {src} | {c['weeks'][0]} to {c['weeks'][1]} | {pos} | {c['players']} | "
                         f"{_pct(c['median_shift'])} | {_pct(c['robust_sd'])} |")
    L.append("")
    L.append("The ESPN median shifts of about 20% between weeks 3, 4 and 5 are the GAP-GAMES-REMAINING-STALE "
             "denominator, not projection changes; demeaning removes them.")
    L.append("")
    L.append("## Realized weekly noise of starters (2024-2025, sd over mean of weekly points)")
    L.append("")
    L.append("| Position | Median | Players |")
    L.append("| --- | --- | --- |")
    for pos in POSITIONS:
        c = doc["weekly_noise"][pos]
        L.append(f"| {pos} | {_pct(c['median_cv'], 0)} | {c['players']} |")
    L.append("")
    L.append("Weekly noise is what a manager faces on Sunday. It is several times the level uncertainty "
             "above and is not what sigma in the spec measures (ES-5).")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- main


def derive(actuals, schedule, byes_doc, players, history, teams=12, scoring="ppr", content_week=None) -> dict:
    sizes = pool_sizes(teams)
    if content_week is None:
        content_week = max(history) if history else 5
    first_ros = content_week + 1
    last_week = byes_doc["regular_season_weeks"][1]
    byes = bye_share(byes_doc["byes"], first_ros, last_week)
    m = pooled_rates(actuals, schedule, sizes, scoring=scoring)
    cross = cross_source_sigma(players, sizes, scoring)
    pos_of = {p["player_key"]: p["pos"] for p in players}
    movement = week_to_week_sigma(history, pos_of, SCORINGS.index(scoring))
    horizon = (last_week - first_ros + 1) / 2.0
    movement_summary = summarize_movement(movement, horizon)
    noise = weekly_noise(actuals, schedule, sizes, scoring=scoring)
    rec = recommend(m, cross, movement_summary, byes)
    return {"schema": SCHEMA, "content_week": content_week, "teams": teams, "scoring": scoring,
            "pool_sizes": sizes, "recommended": rec, "bye_share": byes, "missed_games": m,
            "cross_source": cross, "week_to_week": movement, "week_to_week_summary": movement_summary,
            "weekly_noise": noise,
            "inputs": {"actuals": str(ACTUALS.relative_to(REPO)), "schedule": str(SCHEDULE.relative_to(REPO)),
                       "players": str(PLAYERS.relative_to(REPO)), "history_weeks": sorted(history)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--teams", type=int, default=12)
    ap.add_argument("--scoring", choices=SCORINGS, default="ppr")
    ap.add_argument("--content-week", type=int, default=None)
    ap.add_argument("--config-out", type=Path, default=CONFIG,
                    help="the committed parameters file the engine reads (ES-1); '' to skip")
    args = ap.parse_args(argv)
    actuals = load_actuals()
    schedule = load_schedule()
    byes_doc = json.loads(BYES.read_text(encoding="utf-8"))
    players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    history = load_history()
    doc = derive(actuals, schedule, byes_doc, players, history, args.teams, args.scoring, args.content_week)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(doc), encoding="utf-8")
    if str(args.config_out):
        cfg = {"schema": "lineup-parameters-config/1", "content_week": doc["content_week"],
               "source": "pipelines/derive_lineup_parameters.py (docs/methodology.md ES-1); generated, do not edit",
               "bye_share": doc["bye_share"]["share"],
               "positions": {p: {"m": doc["recommended"][p]["m"], "sigma_rel": doc["recommended"][p]["sigma_rel"],
                                 "sigma_floor": doc["recommended"][p]["sigma_floor"]} for p in POSITIONS}}
        Path(args.config_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.config_out).write_text(json.dumps(cfg, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for pos in POSITIONS:
        r = doc["recommended"][pos]
        print(f"{pos}: m={r['m']:.3f} sigma_rel={r['sigma_rel']:.3f} (now {r['sigma_rel_now']:.3f}, "
              f"drift {r['sigma_rel_drift']:.3f}) floor={r['sigma_floor']:.2f}")
    print(f"bye share {doc['bye_share']['share']:.4f}; wrote {args.out} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
