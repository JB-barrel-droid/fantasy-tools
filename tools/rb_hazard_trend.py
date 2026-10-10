#!/usr/bin/env python3
"""Is the recent drop in running back missed games structural or variance? (JEG-525 item d)

Reads the same inputs as pipelines/derive_lineup_parameters.py (nflverse
2015-2025 weekly actuals and schedule) and the same healthy-starter
selection (weeks 1-5 and 1-9, measured to the season's last week minus
one, 12-team pool sizes). For each season and position it reports:

  * the pooled missed-game rate and a 95% interval from a player-cluster
    bootstrap (missed games come in runs: one season-ending injury is many
    missed games, so a plain binomial interval is far too narrow);
  * a trend test: the slope of the per-season rate on the season (weighted
    least squares, weights = team games), with a bootstrap interval and a
    permutation p-value (seasons shuffled);
  * an over-dispersion test: are the per-season rates further apart than the
    within-season cluster noise alone would produce? (Cochran's Q on the
    bootstrap variances);
  * the candidate m_RB values: all eleven seasons, recency-weighted
    (half-life 3 and 5 seasons), 2022-2025, 2024-2025;
  * the bench-share effect of each candidate at 12-team full PPR, through
    pipelines/expected_starts_model.py (needs output/lineup-parameters.json
    from derive_lineup_parameters.py).

Usage: python3 tools/rb_hazard_trend.py [--out output/rb-hazard-trend.json]
       [--report output/rb-hazard-trend.md] [--boot 2000]
Analysis only; exit 0.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import derive_lineup_parameters as dl  # noqa: E402

SEASONS = dl.HISTORY_SEASONS
POSITIONS = dl.POSITIONS


def per_player_cells(actuals, schedule, sizes, scoring="ppr"):
    """{pos: {season: [(missed, games), ...]}} one entry per selected player and
    window, the exact selection of dl.missed_game_rates."""
    out = {p: defaultdict(list) for p in POSITIONS}
    for season in SEASONS:
        last = dl.last_measured_week(schedule, season)
        sched = schedule[season]
        for lo, hi in dl.SELECTION_WINDOWS:
            sel, sel_teams = dl._player_weeks(actuals, season, lo, hi, scoring)
            meas, _ = dl._player_weeks(actuals, season, hi + 1, last, scoring)
            for pos in POSITIONS:
                cands = []
                for key, weeks in sel.items():
                    if key[1] != pos or len(weeks) < dl.MIN_GAMES:
                        continue
                    team = sel_teams[key].most_common(1)[0][0]
                    if team not in sched:
                        continue
                    team_weeks = [w for w in sched[team] if w <= hi]
                    if not team_weeks or team_weeks[-1] not in weeks:
                        continue
                    cands.append((key, team, statistics.mean(weeks.values())))
                cands.sort(key=lambda c: (-c[2], c[0][0]))
                for key, team, _ in cands[:sizes[pos]["starters"]]:
                    tg = [w for w in sched[team] if hi + 1 <= w <= last]
                    missed = sum(1 for w in tg if w not in meas.get(key, {}))
                    out[pos][season].append((missed, len(tg)))
    return out


def rate(cells):
    g = sum(c[1] for c in cells)
    return sum(c[0] for c in cells) / g if g else float("nan")


def boot_rate(cells, rng, n, sort=True):
    vals = []
    for _ in range(n):
        s = [cells[rng.randrange(len(cells))] for _ in cells]
        vals.append(rate(s))
    if sort:
        vals.sort()
    return vals


def wls_slope(xs, ys, ws):
    sw = sum(ws)
    mx = sum(w * x for x, w in zip(xs, ws)) / sw
    my = sum(w * y for y, w in zip(ys, ws)) / sw
    num = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws))
    den = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws))
    return num / den


def recency_weighted(by_season, half_life):
    """Rate with each season's team games weighted by 0.5 ** (age / half_life),
    age 0 = the latest season."""
    last = max(by_season)
    num = den = 0.0
    for s, cells in by_season.items():
        w = 0.5 ** ((last - s) / half_life)
        num += w * sum(c[0] for c in cells)
        den += w * sum(c[1] for c in cells)
    return num / den


def analyse(cells, boot=2000, seed=521):
    rng = random.Random(seed)
    res = {}
    for pos in POSITIONS:
        by = cells[pos]
        seasons = sorted(by)
        per = []
        boots = {}
        for s in seasons:
            b = boot_rate(by[s], rng, boot)
            boots[s] = b
            per.append({"season": s, "rate": rate(by[s]), "games": sum(c[1] for c in by[s]),
                        "players": len(by[s]),
                        "ci95": [b[int(0.025 * boot)], b[int(0.975 * boot) - 1]],
                        "se": statistics.stdev(b)})
        xs = [r["season"] for r in per]
        ys = [r["rate"] for r in per]
        ws = [r["games"] for r in per]
        slope = wls_slope(xs, ys, ws)
        # bootstrap the slope: resample players within each season
        bs = []
        for i in range(boot):
            ys_b = [boots[s][rng.randrange(boot)] for s in seasons]
            bs.append(wls_slope(xs, ys_b, ws))
        bs.sort()
        # permutation p-value: shuffle which season each rate belongs to
        perm_ge = 0
        n_perm = 5000
        for _ in range(n_perm):
            ys_p = ys[:]
            rng.shuffle(ys_p)
            if abs(wls_slope(xs, ys_p, ws)) >= abs(slope) - 1e-15:
                perm_ge += 1
        # Cochran's Q with bootstrap (cluster) variances: over-dispersion across seasons
        inv = [1 / r["se"] ** 2 for r in per]
        pooled = sum(i * y for i, y in zip(inv, ys)) / sum(inv)
        Q = sum(i * (y - pooled) ** 2 for i, y in zip(inv, ys))
        df = len(per) - 1
        p_q = chi2_sf(Q, df)
        i2 = max(0.0, (Q - df) / Q) if Q > 0 else 0.0
        all_cells = [c for s in seasons for c in by[s]]
        early = [c for s in seasons if s <= 2021 for c in by[s]]
        late = [c for s in seasons if s >= 2022 for c in by[s]]
        b_e, b_l = boot_rate(early, rng, boot, sort=False), boot_rate(late, rng, boot, sort=False)
        diff = sorted(l - e for e, l in zip(b_e, b_l))
        res[pos] = {
            "per_season": per,
            "pooled": rate(all_cells),
            "pooled_ci95_cluster": (lambda b: [b[int(0.025 * boot)], b[int(0.975 * boot) - 1]])(boot_rate(all_cells, rng, boot)),
            "slope_per_season": slope,
            "slope_ci95": [bs[int(0.025 * boot)], bs[int(0.975 * boot) - 1]],
            "slope_perm_p": perm_ge / n_perm,
            "cochran_q": Q, "q_df": df, "q_p": p_q, "i2": i2,
            "early_2015_2021": rate(early), "late_2022_2025": rate(late),
            "late_minus_early_ci95": [diff[int(0.025 * boot)], diff[int(0.975 * boot) - 1]],
            "candidates": {
                "all seasons 2015-2025": rate(all_cells),
                "recency weight, half-life 5 seasons": recency_weighted(by, 5),
                "recency weight, half-life 3 seasons": recency_weighted(by, 3),
                "2022-2025": rate(late),
                "2024-2025": rate([c for s in (2024, 2025) for c in by[s]]),
            },
        }
    return res


def chi2_sf(x, k):
    """Survival function of chi-square with k degrees of freedom (series for
    the regularized lower gamma)."""
    if x <= 0:
        return 1.0
    a = k / 2.0
    xx = x / 2.0
    term = 1.0 / a
    total = term
    n = 1
    while n < 500:
        term *= xx / (a + n)
        total += term
        if term < total * 1e-14:
            break
        n += 1
    lower = total * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
    return max(0.0, 1.0 - lower)


def bench_effect(candidates):
    """Bench tier, fill-in share and RB starter/bench price at 12-team full PPR
    with m_RB set to each candidate (other parameters as recommended)."""
    import expected_starts_model as es
    import value_reference as ref
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    params = es.load_params()
    sources, _ = es.load_sources(inp, "ppr", 12)
    cs = es.chart_sigma_from(sources, 12)
    tiers = es.tiers_on_mean(sources, 12)
    keys = sorted(tiers)
    out = {}
    for label, m in candidates.items():
        prm = {"bye": params["bye"], **{p: dict(params[p]) for p in POSITIONS}}
        prm["RB"]["m"] = m
        r = es.run_setting(sources, 12, prm, cs, "A")
        met = es.shares_and_ratio(es.ddf_mean(r["adjusted"], keys), tiers, 12)
        out[label] = {"m_RB": m, "bench_tier_share": met["bench_tier_share_overall"],
                      "rb_bench_tier_share": met["bench_tier_share"]["RB"],
                      "fill_state_share": sum(v for g, v in r["weights"].items() if g.endswith("|bench")),
                      "rb_price": met["starter_to_bench_price"]["RB"]}
    return out


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def render(doc):
    L = ["# Running back missed games: structural or variance? (JEG-525 item d)", "",
         "Produced by `tools/rb_hazard_trend.py` on `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`, "
         "the same healthy-starter selection as `derive_lineup_parameters.py` (ES-1). Intervals are "
         f"player-cluster bootstraps ({doc['boot']} draws).", "",
         "## Per season, healthy starters (both selection windows pooled)", "",
         "| Season | " + " | ".join(POSITIONS) + " |", "| --- |" + " --- |" * len(POSITIONS)]
    for i, s in enumerate(SEASONS):
        row = []
        for p in POSITIONS:
            r = doc["analysis"][p]["per_season"][i]
            row.append(f"{pct(r['rate'])} ({pct(r['ci95'][0], 0)}-{pct(r['ci95'][1], 0)})")
        L.append(f"| {s} | " + " | ".join(row) + " |")
    L += ["", "## Tests", "",
          "| Position | Pooled (cluster 95%) | Trend per season (95%) | Trend permutation p | Over-dispersion Q (df), p | I-squared | 2015-2021 | 2022-2025 | Difference (95%) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in POSITIONS:
        a = doc["analysis"][p]
        L.append(f"| {p} | {pct(a['pooled'])} ({pct(a['pooled_ci95_cluster'][0])}-{pct(a['pooled_ci95_cluster'][1])}) | "
                 f"{100 * a['slope_per_season']:+.2f} pts ({100 * a['slope_ci95'][0]:+.2f} to {100 * a['slope_ci95'][1]:+.2f}) | "
                 f"{a['slope_perm_p']:.2f} | {a['cochran_q']:.1f} ({a['q_df']}), {a['q_p']:.3f} | {pct(a['i2'], 0)} | "
                 f"{pct(a['early_2015_2021'])} | {pct(a['late_2022_2025'])} | "
                 f"{100 * (a['late_2022_2025'] - a['early_2015_2021']):+.1f} pts ({100 * a['late_minus_early_ci95'][0]:+.1f} to {100 * a['late_minus_early_ci95'][1]:+.1f}) |")
    L += ["", "## Candidate m_RB and the bench-share effect (12-team full PPR, Week 5)", "",
          "| Candidate | m_RB | Bench tier (all positions) | RB bench tier | Pie on fill-in parts | RB starter/bench price |",
          "| --- | --- | --- | --- | --- | --- |"]
    for label, e in doc["bench_effect"].items():
        L.append(f"| {label} | {pct(e['m_RB'])} | {pct(e['bench_tier_share'], 2)} | {pct(e['rb_bench_tier_share'], 2)} | "
                 f"{pct(e['fill_state_share'], 2)} | {e['rb_price']:.2f}x |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO / "output" / "rb-hazard-trend.json")
    ap.add_argument("--report", type=Path, default=REPO / "output" / "rb-hazard-trend.md")
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args(argv)
    actuals = dl.load_actuals_nflverse()
    schedule = dl.load_schedule(dl.HISTORY_SCHEDULE)
    cells = per_player_cells(actuals, schedule, dl.pool_sizes(12))
    analysis = analyse(cells, args.boot)
    effect = bench_effect(analysis["RB"]["candidates"])
    doc = {"boot": args.boot, "analysis": analysis, "bench_effect": effect}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    args.report.write_text(render(doc), encoding="utf-8")
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
