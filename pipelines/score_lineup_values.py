#!/usr/bin/env python3
"""Score value sets against realized lineup points (JEG-521 G6). A report, not a gate.

For every content week that has both saved inputs (data/history/week-N.json)
and realized player-game points (data/inputs/weekly_actuals_2024_2026.csv,
exported from Supabase public.v_player_game_actuals; G4 extends it), build
the value sets from that week's inputs alone and score them on what happened
from that week on:

  1. Usable points. Twelve rosters are drafted by snake order on each value
     set (default roster, position caps), then each week the lineup is the
     roster's best available players by that week's mean projection; a bench
     player's realized points count only in weeks he is in the lineup. The
     score is the Spearman rank correlation between a player's value and his
     realized usable points, per position and overall, with the mean absolute
     rank error. Availability on game day is read from the actuals (a player
     with a stat line played), which a manager knows at kickoff but which this
     harness knows after the fact; it is the one leak and is named in the
     report.
  2. Start-worthy calibration. Players are binned by the expected-starts
     P(level above the starter line) at the valuation week; the realized rate
     is the share of their later team games in which they scored inside the
     position's starter count that week.
  3. Missed-game calibration. The share of later team games missed by the
     players the value set ranks as starters, against the m_pos the parameters
     assume.

  4. Projected-start calibration (MR-23, needs G4 b). The same bins of
     P(start-worthy), against the share of later team games in which ESPN's
     weekly projection for that week put the player inside the position's
     starter count. This is what the share predicts: the start decision is
     made on projections before the week, not on outcomes.
  5. Weekly projection error by position (G6): ESPN's weekly projection
     against the realized points, for players with a stat line, overall and
     among the players projected to start.

Weekly projections come from data/inputs/espn_weekly_projections_2026.csv
(G4 b, refreshed from Supabase public.projection_snapshots by
pipelines/export_weekly_store.py): the last snapshot before the player's
kickoff; rows marked pre_kickoff=false (the 2026-10 backfill of played weeks)
are used and counted in the report. Basis: per scheduled team week (MR-20).
Steps 4 and 5 are skipped when the file is absent.

Value sets scored (all built from the saved week's inputs, 12-team full PPR
by default): expected-starts option A (docs/methodology.md ES-5), the VP
slices as written (OC-2 A), plain value above waivers, and the mean
projection itself as the baseline.

Usage:
    python3 pipelines/score_lineup_values.py [--season 2026] [--teams 12] [--scoring ppr]
        [--out output/lineup-score.json] [--report output/lineup-score.md]

Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import derive_lineup_parameters as dl  # noqa: E402
import expected_starts_model as es  # noqa: E402

OUT = REPO / "output" / "lineup-score.json"
REPORT = REPO / "output" / "lineup-score.md"
SCHEMA = "lineup-score/1"
POSITIONS = es.POSITIONS
SCORING_INDEX = {"standard": 0, "half_ppr": 1, "ppr": 2}
# Draft caps per team on the default roster (starters plus a bench spread).
CAPS = {"QB": 2, "RB": 6, "WR": 7, "TE": 2}
LAST_WEEK = 17
BINS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))
WEEKLY_PROJECTIONS = REPO / "data" / "inputs" / "espn_weekly_projections_2026.csv"
CSV_SCORING = {"standard": "std", "half_ppr": "half_ppr", "ppr": "ppr"}


# ------------------------------------------------------------------ inputs

def history_week(doc: dict, pos_of: dict, scoring: str) -> list:
    """SourceLists for one saved week: projections (ppg) and charts (natives)."""
    idx = SCORING_INDEX[scoring]
    sources = []
    for key, entry in doc["sources"].items():
        if entry.get("kind") == "projection":
            natives = {int(k): v[idx] for k, v in entry["ppg"].items() if v[idx] is not None}
            sources.append(es.SourceLists(natives, pos_of, "projection", key))
        elif entry.get("kind") == "published_chart":
            nat = (entry.get("natives") or {}).get(scoring) or {}
            natives = {int(k): float(v) for k, v in nat.items() if v is not None}
            if natives:
                sources.append(es.SourceLists(natives, pos_of, "chart", key))
    return sources


def actuals_by_week(rows: list, season: int, scoring: str) -> dict:
    """{week: {player_key: points}} for one season."""
    out = defaultdict(dict)
    for r in rows:
        if r["season"] == season:
            out[r["week"]][r["player_key"]] = r["pts"][scoring]
    return out


def team_of(rows: list, season: int) -> dict:
    """{player_key: most frequent team that season}."""
    c = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["season"] == season:
            c[r["player_key"]][r["team"]] += 1
    return {k: max(v, key=v.get) for k, v in c.items()}


def load_weekly_projections(path=WEEKLY_PROJECTIONS, scoring: str = "ppr", season: int = 2026):
    """-> ({week: {player_key: projected points}}, {"rows", "pre_kickoff_false"}),
    or ({}, None) when the file is absent (G4 b not yet stored)."""
    import csv
    path = Path(path)
    if not path.exists():
        return {}, None
    out, n, post = defaultdict(dict), 0, 0
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if int(r["season"]) != season:
                continue
            out[int(r["week"])][int(r["player_key"])] = float(r[CSV_SCORING[scoring]])
            n += 1
            post += r.get("pre_kickoff") == "false"
    return dict(out), {"rows": n, "pre_kickoff_false": post}


# ------------------------------------------------------------------ value sets

def value_sets(sources: list, teams: int, params: dict) -> dict:
    """{name: {key: value}} plus the expected-starts start-worthy probabilities."""
    chart_sigma = es.chart_sigma_from(sources, teams) if any(s.family == "chart" for s in sources) else \
        {p: {"sigma_rel": 0.3, "sigma_floor": 0.0, "floor_frac": 0.0} for p in POSITIONS}
    tiers = es.tiers_on_mean(sources, teams)
    keys = sorted(tiers)
    out = {}
    run_a = es.run_setting(sources, teams, params, chart_sigma, "A")
    out["expected_starts_A"] = es.ddf_mean(run_a["adjusted"], keys)
    run_s = es.run_setting(sources, teams, params, chart_sigma, "B")  # slices with A's budget; use raw slices below
    # VP slices as written: variant 'S' is the slices without the option-B reweight.
    slices = _slices_as_written(sources, teams, run_s["pie"])
    out["vp_slices_OC2A"] = es.ddf_mean(slices, keys)
    plain = {}
    for src in sources:
        counts = es.alloc({p: src.values(p) for p in POSITIONS}, teams)
        vals = {}
        for p in POSITIONS:
            w, _ = es.lines(src.values(p), counts[p]["starters"], counts[p]["rostered"])
            for k, x in src.lists[p]:
                vals[k] = max(0.0, x - w) if w is not None else 0.0
        tot = sum(vals.values())
        plain[src.key] = {k: v * run_a["pie"] / tot for k, v in vals.items()} if tot else vals
    out["plain_value_above_waivers"] = es.ddf_mean(plain, keys)
    out["mean_projection"] = {k: tiers[k]["mean"] for k in keys}
    # Start-worthy probability from the projections (mean over projection sources).
    psw = defaultdict(list)
    for src in sources:
        if src.family != "projection":
            continue
        for p in POSITIONS:
            comps = run_a["per_source"][src.key][p]["es"]["players"]
            for k, comp in zip(src.keys(p), comps):
                psw[k].append(comp["starter_part"] / (comp["v"] * run_a["per_source"][src.key][p]["es"]["avail"])
                              if comp["v"] > 0 else None)
    start_worthy = {k: statistics.mean(v for v in vs if v is not None) for k, vs in psw.items()
                    if any(v is not None for v in vs)}
    return {"values": out, "tiers": tiers, "start_worthy": start_worthy}


def _slices_as_written(sources, teams, pie) -> dict:
    adjusted = {}
    acc = defaultdict(list)
    per = {}
    for src in sources:
        counts = es.alloc({p: src.values(p) for p in POSITIONS}, teams)
        G, comps = {}, {}
        for p in POSITIONS:
            sl = es.slice_components(src.values(p), counts[p]["starters"], counts[p]["rostered"])["players"]
            comps[p] = sl
            G[(p, "starter")] = sum(x["starter_part"] for x in sl)
            G[(p, "bench")] = sum(x["bench_part"] for x in sl)
        tot = sum(G.values())
        if tot > 0:
            for g, v in G.items():
                acc[g].append(v / tot)
        per[src.key] = (G, comps)
    W = {g: statistics.mean(v) for g, v in acc.items()}
    s = sum(W.values())
    W = {g: v / s for g, v in W.items()}
    for src in sources:
        G, comps = per[src.key]
        vals = {}
        for p in POSITIONS:
            bs, bb = pie * W.get((p, "starter"), 0), pie * W.get((p, "bench"), 0)
            gs, gb = G[(p, "starter")], G[(p, "bench")]
            if gs <= 0 and gb > 0:
                bb, bs = bb + bs, 0.0
            if gb <= 0 and gs > 0:
                bs, bb = bs + bb, 0.0
            rs = bs / gs if gs > 0 else 0.0
            rb = bb / gb if gb > 0 else 0.0
            for k, c in zip(src.keys(p), comps[p]):
                vals[k] = rs * c["starter_part"] + rb * c["bench_part"]
        adjusted[src.key] = vals
    return adjusted


# ------------------------------------------------------------------ simulation

def snake_draft(values: dict, pos_of: dict, teams: int, caps=CAPS, roster_size=14) -> list:
    """teams rosters (lists of keys) by snake order on `values`, best available
    under the position caps."""
    order = sorted((k for k, v in values.items() if v is not None and k in pos_of), key=lambda k: (-values[k], k))
    rosters = [[] for _ in range(teams)]
    counts = [defaultdict(int) for _ in range(teams)]
    taken = set()
    rounds = roster_size
    for rnd in range(rounds):
        seq = range(teams) if rnd % 2 == 0 else range(teams - 1, -1, -1)
        for t in seq:
            for k in order:
                if k in taken:
                    continue
                p = pos_of[k]
                if counts[t][p] >= caps.get(p, 0):
                    continue
                rosters[t].append(k)
                counts[t][p] += 1
                taken.add(k)
                break
    return rosters


def lineup(roster: list, pos_of: dict, projection: dict, available: set, shape=es.ROSTER) -> list:
    """The roster's starters this week: dedicated slots by projection among
    available players, then the flex by the best remaining RB/WR/TE."""
    avail = [k for k in roster if k in available]
    avail.sort(key=lambda k: -(projection.get(k) or 0.0))
    starters, used = [], set()
    for p in POSITIONS:
        n = shape[p]
        for k in avail:
            if n == 0:
                break
            if pos_of[k] == p and k not in used:
                starters.append(k)
                used.add(k)
                n -= 1
    n = shape["FLEX"]
    for k in avail:
        if n == 0:
            break
        if pos_of[k] in es.FLEX_ELIGIBLE and k not in used:
            starters.append(k)
            used.add(k)
            n -= 1
    return starters


def usable_points(values: dict, pos_of: dict, teams: int, weekly_actuals: dict, weekly_projection: dict,
                  weeks: list) -> dict:
    """{key: {usable, total, starts, games}} over `weeks`, from a snake draft on
    `values` and weekly lineups by `weekly_projection[week]` among players
    with a stat line that week."""
    rosters = snake_draft(values, pos_of, teams)
    out = {k: {"usable": 0.0, "total": 0.0, "starts": 0, "weeks_available": 0}
           for r in rosters for k in r}
    for w in weeks:
        act = weekly_actuals.get(w, {})
        proj = weekly_projection.get(w, {})
        for roster in rosters:
            starters = set(lineup(roster, pos_of, proj, set(act)))
            for k in roster:
                if k in act:
                    out[k]["total"] += act[k]
                    out[k]["weeks_available"] += 1
                    if k in starters:
                        out[k]["usable"] += act[k]
                        out[k]["starts"] += 1
    return out


# ------------------------------------------------------------------ scoring

def spearman(xs: list, ys: list) -> float | None:
    n = len(xs)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for t in range(i, j + 1):
                r[order[t]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def score_usable(values: dict, usable: dict, pos_of: dict) -> dict:
    out = {}
    for p in list(POSITIONS) + ["ALL"]:
        keys = [k for k in usable if (p == "ALL" or pos_of.get(k) == p) and values.get(k) is not None]
        xs = [values[k] for k in keys]
        ys = [usable[k]["usable"] for k in keys]
        rho = spearman(xs, ys)
        out[p] = {"players": len(keys), "spearman": rho,
                  "usable_points": sum(ys), "total_points": sum(usable[k]["total"] for k in keys)}
    return out


def start_worthy_calibration(start_worthy: dict, pos_of: dict, weekly_actuals: dict, weeks: list,
                             starters_per_pos: dict, team_of_key: dict, schedule: dict) -> list:
    """Bins of predicted P(start-worthy) against the realized share of later
    team games with a finish inside the position's starter count."""
    starter_line = {}
    for w in weeks:
        act = weekly_actuals.get(w, {})
        for p in POSITIONS:
            vals = sorted((v for k, v in act.items() if pos_of.get(k) == p), reverse=True)
            n = starters_per_pos.get(p, 0)
            if n <= 0 or not vals:
                starter_line[(w, p)] = math.inf
            else:
                starter_line[(w, p)] = vals[n - 1] if len(vals) >= n else vals[-1]
    rows = []
    for lo, hi in BINS:
        hits = games = n_players = 0
        for k, prob in start_worthy.items():
            if not (lo <= prob < hi) or k not in pos_of:
                continue
            team = team_of_key.get(k)
            if team is None or team not in schedule:
                continue
            n_players += 1
            for w in weeks:
                if w not in schedule[team]:
                    continue
                games += 1
                pts = weekly_actuals.get(w, {}).get(k)
                if pts is not None and pts >= starter_line[(w, pos_of[k])]:
                    hits += 1
        rows.append({"bin": [lo, min(hi, 1.0)], "players": n_players, "team_games": games,
                     "realized_start_worthy_rate": (hits / games) if games else None})
    return rows


def projected_starters(weekly_projection: dict, pos_of: dict, weeks: list, starters_per_pos: dict) -> dict:
    """{week: set(player_key)}: inside the position's starter count by that
    week's projection (players ESPN projects at 0 or not at all are not)."""
    out = {}
    for w in weeks:
        proj = weekly_projection.get(w, {})
        chosen = set()
        for p in POSITIONS:
            ranked = sorted((k for k, v in proj.items() if pos_of.get(k) == p and v > 0),
                            key=lambda k: -proj[k])
            chosen.update(ranked[:starters_per_pos.get(p, 0)])
        out[w] = chosen
    return out


def projected_start_calibration(start_worthy: dict, pos_of: dict, weekly_projection: dict, weeks: list,
                                starters_per_pos: dict, team_of_key: dict, schedule: dict) -> list:
    """Bins of predicted P(start-worthy) against the realized share of later
    team games in which the weekly projection put the player inside the
    starter count (MR-23: the thing the share predicts)."""
    weeks = [w for w in weeks if w in weekly_projection]
    chosen = projected_starters(weekly_projection, pos_of, weeks, starters_per_pos)
    rows = []
    for lo, hi in BINS:
        hits = games = n_players = 0
        for k, prob in start_worthy.items():
            if not (lo <= prob < hi) or k not in pos_of:
                continue
            team = team_of_key.get(k)
            if team is None or team not in schedule:
                continue
            n_players += 1
            for w in weeks:
                if w not in schedule[team]:
                    continue
                games += 1
                hits += k in chosen[w]
        rows.append({"bin": [lo, min(hi, 1.0)], "players": n_players, "team_games": games,
                     "realized_projected_start_rate": (hits / games) if games else None})
    return rows


def projection_error(weekly_projection: dict, weekly_actuals: dict, pos_of: dict, weeks: list,
                     starters_per_pos: dict) -> dict:
    """Per position: mean error (projection minus actual), mean absolute
    error and n, for player-weeks with a projection above 0 and a stat line
    (conditional on playing: a projected player who sat is left out);
    `starters` restricts to the players projected inside the starter count."""
    chosen = projected_starters(weekly_projection, pos_of, weeks, starters_per_pos)
    acc = defaultdict(lambda: {"all": [], "starters": []})
    for w in weeks:
        proj, act = weekly_projection.get(w, {}), weekly_actuals.get(w, {})
        for k, v in proj.items():
            if v <= 0 or k not in act or pos_of.get(k) not in POSITIONS:
                continue
            d = v - act[k]
            acc[pos_of[k]]["all"].append(d)
            if k in chosen.get(w, ()):
                acc[pos_of[k]]["starters"].append(d)

    def stats(ds):
        if not ds:
            return {"n": 0, "mean_error": None, "mean_abs_error": None}
        return {"n": len(ds), "mean_error": sum(ds) / len(ds),
                "mean_abs_error": sum(abs(d) for d in ds) / len(ds)}
    return {p: {g: stats(acc[p][g]) for g in ("all", "starters")} for p in POSITIONS}


def missed_game_calibration(values: dict, pos_of: dict, starters_per_pos: dict, weekly_actuals: dict,
                            weeks: list, team_of_key: dict, schedule: dict, params: dict) -> dict:
    out = {}
    for p in POSITIONS:
        ranked = sorted((k for k in values if values[k] is not None and pos_of.get(k) == p),
                        key=lambda k: -values[k])[:starters_per_pos.get(p, 0)]
        games = missed = 0
        for k in ranked:
            team = team_of_key.get(k)
            if team is None or team not in schedule:
                continue
            for w in weeks:
                if w in schedule[team]:
                    games += 1
                    if k not in weekly_actuals.get(w, {}):
                        missed += 1
        out[p] = {"starters": len(ranked), "team_games": games, "missed": missed,
                  "realized_rate": (missed / games) if games else None, "assumed_m": (params.get(p) or {}).get("m")}
    return out


# ------------------------------------------------------------------ run

def run(season: int, teams: int, scoring: str, params: dict, history: dict, players: list, actuals: list,
        schedule: dict, last_week: int = LAST_WEEK, weekly_projection: dict | None = None,
        weekly_projection_meta: dict | None = None) -> dict:
    pos_of = {p["player_key"]: p["pos"] for p in players}
    acts = actuals_by_week(actuals, season, scoring)
    team_key = team_of(actuals, season)
    sched = schedule.get(season, {})
    weeks_with_actuals = sorted(acts)
    out = {"schema": SCHEMA, "season": season, "teams": teams, "scoring": scoring,
           "weeks_with_actuals": weeks_with_actuals, "valuation_weeks": [], "leak_note":
           "Game-day availability is read from the actuals (a stat line = played): known at kickoff to a "
           "manager, known after the fact here.",
           "weekly_projections": weekly_projection_meta,
           "weeks_with_weekly_projections": sorted(weekly_projection or {})}
    weekly_projection = weekly_projection or {}
    for vw in sorted(history):
        later = [w for w in weeks_with_actuals if vw <= w <= last_week]
        if not later:
            continue
        doc = history[vw]
        sources = history_week(doc, pos_of, scoring)
        if not any(s.family == "projection" for s in sources):
            continue
        vs = value_sets(sources, teams, params)
        tiers = vs["tiers"]
        counts = es.alloc({p: sorted((t["mean"] for t in tiers.values() if t["pos"] == p), reverse=True)
                           for p in POSITIONS}, teams)
        starters_per_pos = {p: counts[p]["starters"] for p in POSITIONS}
        # Lineups each week by that week's own saved mean projection when it exists, else the valuation week's.
        weekly_proj = {}
        for w in later:
            if w in history:
                wt = es.tiers_on_mean(history_week(history[w], pos_of, scoring), teams)
                weekly_proj[w] = {k: t["mean"] for k, t in wt.items()}
            else:
                weekly_proj[w] = vs["values"]["mean_projection"]
        entry = {"valuation_week": vw, "scored_weeks": later, "value_sets": {}}
        for name, values in vs["values"].items():
            usable = usable_points(values, pos_of, teams, acts, weekly_proj, later)
            entry["value_sets"][name] = {"usable": score_usable(values, usable, pos_of),
                                         "missed_games": missed_game_calibration(
                                             values, pos_of, starters_per_pos, acts, later, team_key, sched, params)}
        entry["start_worthy_calibration"] = start_worthy_calibration(
            vs["start_worthy"], pos_of, acts, later, starters_per_pos, team_key, sched)
        if weekly_projection:
            entry["projected_start_calibration"] = projected_start_calibration(
                vs["start_worthy"], pos_of, weekly_projection, later, starters_per_pos, team_key, sched)
            entry["projection_error"] = projection_error(
                weekly_projection, acts, pos_of, [w for w in later if w in weekly_projection], starters_per_pos)
        out["valuation_weeks"].append(entry)
    return out


def render_report(doc: dict) -> str:
    L = [f"# Value sets against realized lineup points, {doc['season']} ({doc['teams']} teams, {doc['scoring']})", ""]
    L.append("Produced by `pipelines/score_lineup_values.py`. A report, not a deploy gate. "
             f"Weeks with actuals: {doc['weeks_with_actuals']}. {doc['leak_note']}")
    for e in doc["valuation_weeks"]:
        L.append("")
        L.append(f"## Valued on Week {e['valuation_week']} inputs, scored on weeks {e['scored_weeks']}")
        L.append("")
        L.append("| Value set | QB rho | RB rho | WR rho | TE rho | All rho | Usable points | Rostered points |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for name, r in e["value_sets"].items():
            u = r["usable"]
            def f(x):
                return "n/a" if x is None else f"{x:.3f}"
            L.append(f"| {name} | " + " | ".join(f(u[p]["spearman"]) for p in POSITIONS)
                     + f" | {f(u['ALL']['spearman'])} | {u['ALL']['usable_points']:.0f} | {u['ALL']['total_points']:.0f} |")
        L.append("")
        L.append("Missed games among the players each set ranks as starters (realized vs assumed m):")
        L.append("")
        L.append("| Value set | QB | RB | WR | TE |")
        L.append("| --- | --- | --- | --- | --- |")
        for name, r in e["value_sets"].items():
            m = r["missed_games"]
            L.append(f"| {name} | " + " | ".join(
                ("n/a" if m[p]["realized_rate"] is None else f"{100 * m[p]['realized_rate']:.1f}% vs {100 * m[p]['assumed_m']:.1f}%")
                for p in POSITIONS) + " |")
        L.append("")
        L.append("Start-worthy calibration (expected-starts P(level above the starter line) at valuation vs realized share of later team games with a finish inside the starter count):")
        L.append("")
        L.append("| Predicted bin | Players | Team games | Realized |")
        L.append("| --- | --- | --- | --- |")
        for b in e["start_worthy_calibration"]:
            rr = b["realized_start_worthy_rate"]
            L.append(f"| {b['bin'][0]:.1f} to {b['bin'][1]:.1f} | {b['players']} | {b['team_games']} | "
                     + ("n/a" if rr is None else f"{100 * rr:.1f}%") + " |")
        if e.get("projected_start_calibration"):
            L.append("")
            L.append("Projected-start calibration (MR-23: the same bins against the share of later team games in "
                     "which ESPN's weekly projection put the player inside the starter count):")
            L.append("")
            L.append("| Predicted bin | Players | Team games | Projected to start |")
            L.append("| --- | --- | --- | --- |")
            for b in e["projected_start_calibration"]:
                rr = b["realized_projected_start_rate"]
                L.append(f"| {b['bin'][0]:.1f} to {b['bin'][1]:.1f} | {b['players']} | {b['team_games']} | "
                         + ("n/a" if rr is None else f"{100 * rr:.1f}%") + " |")
        if e.get("projection_error"):
            L.append("")
            L.append("ESPN weekly projection minus actual points, player-weeks with a projection above 0 and a stat line. "
                     "Conditional on playing: a player projected to play who then sat has no stat line and is left out, "
                     "so these errors do not include the misses from inactive players.")
            L.append("")
            L.append("| Position | n | Mean error | Mean absolute error | Projected starters n | Starters mean error | Starters mean absolute error |")
            L.append("| --- | --- | --- | --- | --- | --- | --- |")
            for p in POSITIONS:
                a, st = e["projection_error"][p]["all"], e["projection_error"][p]["starters"]
                def g(x):
                    return "n/a" if x is None else f"{x:+.2f}"
                def h(x):
                    return "n/a" if x is None else f"{x:.2f}"
                L.append(f"| {p} | {a['n']} | {g(a['mean_error'])} | {h(a['mean_abs_error'])} | {st['n']} | "
                         f"{g(st['mean_error'])} | {h(st['mean_abs_error'])} |")
    meta = doc.get("weekly_projections")
    if meta:
        L.append("")
        L.append(f"Weekly projections: {meta['rows']} player-weeks from `data/inputs/espn_weekly_projections_2026.csv`, "
                 f"{meta['pre_kickoff_false']} of them read after kickoff (backfilled played weeks; ESPN's stored "
                 "projection for a played week, assumed to be its pre-game one). Basis: per scheduled team week.")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--teams", type=int, default=12)
    ap.add_argument("--scoring", choices=tuple(SCORING_INDEX), default="ppr")
    ap.add_argument("--params", type=Path, default=es.PARAMS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", type=Path, default=REPORT)
    args = ap.parse_args(argv)
    params = es.load_params(args.params)
    history = {}
    for path in sorted(dl.HISTORY.glob("week-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        history[int(doc["week"])] = doc
    players = json.loads(dl.PLAYERS.read_text(encoding="utf-8"))["players"]
    actuals = dl.load_actuals()
    schedule = dl.load_schedule()
    wproj, wmeta = load_weekly_projections(scoring=args.scoring, season=args.season)
    doc = run(args.season, args.teams, args.scoring, params, history, players, actuals, schedule,
              weekly_projection=wproj, weekly_projection_meta=wmeta)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    args.report.write_text(render_report(doc), encoding="utf-8")
    for e in doc["valuation_weeks"]:
        rhos = {n: r["usable"]["ALL"]["spearman"] for n, r in e["value_sets"].items()}
        print(f"week {e['valuation_week']} -> {e['scored_weeks']}: "
              + ", ".join(f"{n} rho={v:.3f}" for n, v in rhos.items() if v is not None))
    print(f"wrote {args.out} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
