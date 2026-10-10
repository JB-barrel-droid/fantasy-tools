#!/usr/bin/env python3
"""Effect of league week inputs on the expected-starts value (JEG-525 item c, MR-22).

Proposed inputs (docs/methodology.md ES-12): content week W, the league's
last regular-season week R and playoff weeks P, and an objective:
"season" (weeks W+1 .. last playoff week), "regular" (W+1 .. R) or
"playoffs" (P only). For each objective this measures, at 12-team full PPR
on the Week 5 build:

  b       bye share of the objective window's team-weeks (byes table 2026);
  sigma   cross-source spread now, plus weekly drift scaled to the window's
          midpoint distance from W (sqrt of weeks ahead), as ES-1 does;
  m       for "season"/"regular", the ES-1 pooled per-game hazard (flat in
          time); for "playoffs", the hazard measured on the playoff weeks
          themselves for players healthy at the end of weeks 1-5 / 1-9
          (2015-2025, same selection as ES-1), which carries the season-
          ending absences that pile up before the playoffs.

and reports the bench tier, the pie on fill-in parts and the RB
starter/bench price. Today's spec ("to week 18") is the first row.

Usage: python3 tools/season_window_effect.py [--report output/season-window-effect.md]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "pipelines"), str(REPO)]
import derive_lineup_parameters as dl  # noqa: E402
import expected_starts_model as es  # noqa: E402
import value_reference as ref  # noqa: E402

W = 5
R = 14
P = (15, 17)


def playoff_hazard(actuals, schedule, sizes, playoff_offset=(15, 17)):
    """Healthy starters selected on weeks 1-5 and 1-9, missed share of team
    games in the season's fantasy playoff weeks. 2015-2020 had a 17-week
    season (fantasy playoffs 14-16); from 2021, 18 weeks (15-17)."""
    acc = {p: Counter() for p in dl.POSITIONS}
    for season in dl.HISTORY_SEASONS:
        final = max(w for weeks in schedule[season].values() for w in weeks)
        lo, hi = (playoff_offset[0] - (18 - final), playoff_offset[1] - (18 - final))
        for s_lo, s_hi in dl.SELECTION_WINDOWS:
            r = dl.missed_game_rates(actuals, schedule, season, (s_lo, s_hi), (lo, hi), sizes)
            for p in dl.POSITIONS:
                acc[p]["missed"] += r[p]["starters"]["missed"]
                acc[p]["games"] += r[p]["starters"]["games"]
    return {p: acc[p]["missed"] / acc[p]["games"] for p in dl.POSITIONS}


def params_for(lp, base, byes, first, last, m_override=None, horizon=None):
    b = dl.bye_share(byes, first, last)["share"] if last >= first else 0.0
    if horizon is None:
        horizon = (last - first + 1) / 2.0
    prm = {"bye": b}
    for p in dl.POSITIONS:
        now = lp["recommended"][p]["sigma_rel_now"]
        wk = lp["week_to_week_summary"][p]["weekly_rel_sd"]
        prm[p] = {"m": (m_override or {}).get(p, base[p]["m"]),
                  "sigma_rel": math.sqrt(now ** 2 + (wk * math.sqrt(horizon)) ** 2),
                  "sigma_floor": base[p]["sigma_floor"]}
    return prm


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=REPO / "output" / "season-window-effect.md")
    args = ap.parse_args(argv)
    lp = json.loads((REPO / "output" / "lineup-parameters.json").read_text())
    base = es.load_params()
    byes = json.loads((REPO / "data" / "inputs" / "nfl_byes_2026.json").read_text())["byes"]
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    sources, _ = es.load_sources(inp, "ppr", 12)
    cs = es.chart_sigma_from(sources, 12)
    tiers = es.tiers_on_mean(sources, 12)
    keys = sorted(tiers)
    hist = dl.load_actuals_nflverse()
    sched = dl.load_schedule(dl.HISTORY_SCHEDULE)
    m_po = playoff_hazard(hist, sched, dl.pool_sizes(12))
    mid_po = (P[0] + P[1]) / 2.0
    cases = [
        ("today's spec: weeks 6-18", params_for(lp, base, byes, W + 1, 18)),
        ("season: weeks 6-17 (regular season and playoffs)", params_for(lp, base, byes, W + 1, P[1])),
        (f"regular season: weeks 6-{R}", params_for(lp, base, byes, W + 1, R)),
        (f"playoffs: weeks {P[0]}-{P[1]}, per-game hazard", params_for(lp, base, byes, P[0], P[1], horizon=mid_po - W)),
        (f"playoffs: weeks {P[0]}-{P[1]}, hazard measured in the playoff weeks",
         params_for(lp, base, byes, P[0], P[1], m_override=m_po, horizon=mid_po - W)),
    ]
    rows = []
    for label, prm in cases:
        r = es.run_setting(sources, 12, prm, cs, "A")
        met = es.shares_and_ratio(es.ddf_mean(r["adjusted"], keys), tiers, 12)
        rows.append({"label": label, "bye": prm["bye"], "m_RB": prm["RB"]["m"], "sigma_RB": prm["RB"]["sigma_rel"],
                     "bench_tier": met["bench_tier_share_overall"],
                     "fill": sum(v for g, v in r["weights"].items() if g.endswith("|bench")),
                     "rb_price": met["starter_to_bench_price"]["RB"]})
    L = ["# League week inputs: effect on the expected-starts value (12-team full PPR, Week 5)", "",
         "Produced by `tools/season_window_effect.py`. Playoff-week hazard of healthy starters (2015-2025): "
         + ", ".join(f"{p} {100 * m_po[p]:.1f}%" for p in dl.POSITIONS) + ".", "",
         "| Objective window | Bye share | m_RB | sigma_RB | Bench tier | Pie on fill-in parts | RB starter/bench price |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        L.append(f"| {r['label']} | {100 * r['bye']:.1f}% | {100 * r['m_RB']:.1f}% | {100 * r['sigma_RB']:.1f}% | "
                 f"{100 * r['bench_tier']:.2f}% | {100 * r['fill']:.2f}% | {r['rb_price']:.2f}x |")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(L) + "\n", encoding="utf-8")
    (REPO / "output" / "season-window-effect.json").write_text(json.dumps({"m_playoff": m_po, "rows": rows}, indent=1))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
