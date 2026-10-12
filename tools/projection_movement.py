#!/usr/bin/env python3
"""How far weekly projections move, and how wrong they are (JEG-540, for JEG-530).

Input: data/inputs/weekly_projections_sleeper.csv.gz (Sleeper's weekly
projections, provider RotoWire, 2018-2026; internal measurement only) and
the nflverse actuals for 2018-2025.

1. Projection movement by horizon. For each player projected in week t at or
   above the position's 12-team bench line that week (rank <= rostered
   count), and again in week t+h of the same season, the relative change
   (p[t+h] - p[t]) / p[t]. Its variance grows with h: var(h) = 2 x matchup
   noise + drift x h (a random-walk level plus independent weekly matchup
   noise). Fitting that line over h = 1..8 separates the two. The drift per
   week is what the expected-starts sigma is meant to be (ES-1: "where his
   projection will sit when the lineup is set"), so it replaces the stand-in
   measured from three weeks of history.
   Players missing in week t+h (injured, benched) are excluded: their move is
   the missed-game hazard m, already priced separately.
2. Weekly projection error against actual points, by position: sd of
   (actual - projection) / projection, for projected starters.
3. The bench share at 12-team full PPR (share form and the upside form) with
   sigma rebuilt from the measured drift, to show where the 9% vs 12%
   question lands on measured numbers.

Usage: python3 tools/projection_movement.py [--report output/projection-movement.md]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "pipelines"), str(REPO)]
import derive_lineup_parameters as dl  # noqa: E402

SLEEPER = REPO / "data" / "inputs" / "weekly_projections_sleeper.csv.gz"
POS = dl.POSITIONS
MAX_H = 8
SEASONS = range(2018, 2026)


def load(path=SLEEPER):
    out = defaultdict(dict)  # (season, sleeper_id) -> {week: row}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["pos"] not in POS:
                continue
            s, w = int(r["season"]), int(r["week"])
            out[(s, r["sleeper_id"])][w] = {"p": float(r["pts_ppr"] or 0), "pos": r["pos"], "gsis": r["gsis_id"],
                                            "name": r["name"], "team": r["team"]}
    return out


def eligible(players, sizes):
    """{(season, week): set of sleeper ids} at or above the 12-team rostered
    line at their position by that week's projection."""
    by = defaultdict(lambda: defaultdict(list))
    for (s, sid), weeks in players.items():
        for w, r in weeks.items():
            by[(s, w)][r["pos"]].append((r["p"], sid))
    out = {}
    for key, poss in by.items():
        keep = set()
        for pos, lst in poss.items():
            lst.sort(reverse=True)
            keep.update(sid for _, sid in lst[:sizes[pos]["rostered"]])
        out[key] = keep
    return out


def movement(players, elig, seasons=SEASONS):
    res = {p: {h: [] for h in range(1, MAX_H + 1)} for p in POS}
    for (s, sid), weeks in players.items():
        if s not in seasons:
            continue
        for t, r in weeks.items():
            if sid not in elig.get((s, t), ()) or r["p"] <= 0:
                continue
            for h in range(1, MAX_H + 1):
                r2 = weeks.get(t + h)
                if r2 and r2["p"] > 0 and t + h <= 17:
                    res[r["pos"]][h].append((r2["p"] - r["p"]) / r["p"])
    out = {}
    for p in POS:
        hs, vs, ns = [], [], []
        for h in range(1, MAX_H + 1):
            x = res[p][h]
            if len(x) > 50:
                med = statistics.median(x)
                mad = statistics.median(abs(v - med) for v in x) * dl.MAD_TO_SD
                hs.append(h); vs.append(mad ** 2); ns.append(len(x))
        # least squares var = a + b h
        mh, mv = statistics.mean(hs), statistics.mean(vs)
        b = sum((h - mh) * (v - mv) for h, v in zip(hs, vs)) / sum((h - mh) ** 2 for h in hs)
        a = mv - b * mh
        out[p] = {"by_h": [{"h": h, "robust_sd": math.sqrt(v), "n": n} for h, v, n in zip(hs, vs, ns)],
                  "drift_var_per_week": max(b, 0.0), "drift_sd_per_week": math.sqrt(max(b, 0.0)),
                  "matchup_sd": math.sqrt(max(a, 0.0) / 2)}
    return out


def projection_error(players, elig):
    """sd of (actual - projection)/projection for eligible player-weeks with a
    matching nflverse row (gsis id, else name + team + season)."""
    act = dl.load_actuals_nflverse()
    by_gsis = {(r["season"], r["week"], r["player_key"]): r["pts"]["ppr"] for r in act}
    import gzip as gz
    names = {}
    with gz.open(dl.HISTORY_ACTUALS, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            names[(int(r["season"]), r["name"].lower().replace(".", ""), r["team"])] = r["player_id"]
    sched = dl.load_schedule(dl.HISTORY_SCHEDULE)
    err = defaultdict(list)
    matched = total = 0
    for (s, sid), weeks in players.items():
        if s not in SEASONS:
            continue
        for w, r in weeks.items():
            if sid not in elig.get((s, w), ()) or r["p"] <= 0:
                continue
            total += 1
            g = r["gsis"] or names.get((s, r["name"].lower().replace(".", ""), r["team"]))
            if not g:
                continue
            a = by_gsis.get((s, w, g))
            if a is None:
                team_weeks = sched.get(s, {}).get(r["team"], [])
                if w not in team_weeks:
                    continue
                continue  # did not play: the hazard, not projection error
            matched += 1
            err[r["pos"]].append((a - r["p"]) / r["p"])
    return {"matched": matched, "eligible": total,
            "by_pos": {p: {"sd": statistics.pstdev(err[p]), "bias": statistics.mean(err[p]), "n": len(err[p])}
                       for p in POS if err[p]}}


def bench_effect(mv):
    """Bench tier at 12-team full PPR with sigma rebuilt from the measured
    drift (cross-source spread now + measured drift over the default horizon)."""
    import expected_starts_model as es
    import value_reference as ref
    cfg = json.loads(dl.CONFIG.read_text(encoding="utf-8"))
    res = dl.resolve(cfg)
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    sources, _ = es.load_sources(inp, "ppr", 12)
    cs = es.chart_sigma_from(sources, 12)
    tiers = es.tiers_on_mean(sources, 12)
    keys = sorted(tiers)
    out = {}
    for label, use_measured in (("stand-in sigma (current spec)", False), ("measured drift (Sleeper weekly projections)", True)):
        prm = {"bye": res["bye"]}
        for p in POS:
            b = cfg["positions"][p]
            weekly = mv[p]["drift_sd_per_week"] if use_measured else b["sigma_weekly"]
            sig = math.sqrt(b["sigma_now"] ** 2 + weekly ** 2 * res["horizon_weeks"])
            prm[p] = {"m": res["positions"][p]["m"], "sigma_rel": sig, "sigma_floor": b["sigma_floor"]}
        row = {"sigma": {p: prm[p]["sigma_rel"] for p in POS}}
        for form in ("share", "option"):
            r = es.run_setting(sources, 12, prm, cs, "A", form)
            met = es.shares_and_ratio(es.ddf_mean(r["adjusted"], keys), tiers, 12)
            row[form] = {"bench": met["bench_tier_share_overall"], "rb_price": met["starter_to_bench_price"]["RB"]}
        out[label] = row
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=REPO / "output" / "projection-movement.md")
    args = ap.parse_args(argv)
    players = load()
    elig = eligible(players, dl.pool_sizes(12))
    mv = movement(players, elig)
    pe = projection_error(players, elig)
    be = bench_effect(mv)
    cfg = json.loads(dl.CONFIG.read_text(encoding="utf-8"))
    L = ["# Weekly projection movement and error (Sleeper weekly projections 2018-2025, full PPR)", "",
         "Produced by `tools/projection_movement.py` (JEG-540). Players at or above the 12-team rostered line "
         "by that week's projection, followed while they keep being projected.", "",
         "## How far a projection moves over h weeks (robust sd of the relative change)", "",
         "| Position | " + " | ".join(f"h={h}" for h in range(1, MAX_H + 1)) + " | Matchup noise (sd) | Level drift per week (sd) | Stand-in drift per week (spec) |",
         "| --- |" + " --- |" * (MAX_H + 3)]
    for p in POS:
        m = mv[p]
        L.append(f"| {p} | " + " | ".join(f"{100 * x['robust_sd']:.0f}%" for x in m["by_h"]) +
                 f" | {100 * m['matchup_sd']:.1f}% | {100 * m['drift_sd_per_week']:.1f}% | "
                 f"{100 * cfg['positions'][p]['sigma_weekly']:.1f}% |")
    L += ["", "## Weekly projection error against actual points (projected rostered players who played)", "",
          f"Matched {pe['matched']:,} of {pe['eligible']:,} eligible player-weeks to nflverse actuals.", "",
          "| Position | sd of (actual - projection) / projection | Mean bias | Player-weeks |", "| --- | --- | --- | --- |"]
    for p, v in pe["by_pos"].items():
        L.append(f"| {p} | {100 * v['sd']:.0f}% | {100 * v['bias']:+.1f}% | {v['n']:,} |")
    L += ["", "## Bench share at 12-team full PPR, Week 5, defaults (season objective)", "",
          "| Uncertainty | sigma QB / RB / WR / TE | Bench share, chance of starting (approved) | Bench share, with the upside | RB starter/bench price, approved | with the upside |",
          "| --- | --- | --- | --- | --- | --- |"]
    for label, r in be.items():
        L.append(f"| {label} | " + " / ".join(f"{100 * r['sigma'][p]:.0f}%" for p in POS) +
                 f" | {100 * r['share']['bench']:.1f}% | {100 * r['option']['bench']:.1f}% | "
                 f"{r['share']['rb_price']:.2f}x | {r['option']['rb_price']:.2f}x |")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(L) + "\n", encoding="utf-8")
    (REPO / "output" / "projection-movement.json").write_text(json.dumps({"movement": mv, "error": pe, "bench": be}, indent=1))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
