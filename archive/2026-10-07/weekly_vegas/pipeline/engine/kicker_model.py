#!/usr/bin/env python3
"""Kicker opportunity model (Project Upright methodology, logic only).

Implements the ten Upright principles for weekly kicker projection:
  1. Team implied points as the opportunity base.
  2. Red-zone stall rate (nflverse red-zone TD efficiency) modulates FG
     attempts: drives that stall in the red zone become FG tries.
  3. Historical analogs: implied total, spread, red-zone efficiency, venue,
     weather, and opponent context select comparable team-games.
  4. Simulation/error bands instead of false ordinal precision: Poisson
     attempts x Binomial makes -> percentile bands.
  5. Weeks 1-4 weight Vegas and conditions over small-sample efficiency.
  6. Shrunk kicker accuracy by distance: (makes + prior) / (att + prior n)
     with league-average priors; new kickers get the league average.
  7. Dome/roof/wind/temperature: Open-Meteo for outdoor venues; wind >15mph
     and cold degrade accuracy and long attempts.
  8. Separate scoring: conventional 3/4/5, flat-3, decimal-distance,
     miss-penalty -- all configurable.
  9. Tiers + top-tier probability/range outputs, not just a point estimate.
 10. Independent backtesting hooks (this module never cites Upright's
     reported results; calibrate and test on our own data).

This module is the LOGIC. Weekly inputs (implied totals, weather, kicker
identity) arrive via build_weekly_kicker_inputs.py; the model's outputs feed
the kicker leg of the Monday/current pipeline as a cross-check, never as a
silent override of the chart's expert projections.

Free-only sources: nflverse (calibration + red-zone), Open-Meteo (weather),
Odds API spreads/totals or manual lines (implied points; quota-guarded).
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, "/home/hatch/workspace/football-signal")
sys.path.insert(0, "/home/hatch/workspace/football-signal/.venv/lib/python3.12/site-packages")

# ---- distance bands (yards) ----
BANDS = ("20_29", "30_39", "40_49", "50_plus")

# League-average FG% by band, calibrated 2024-2025 nflverse play-by-play
# (2306 FG attempts). Recompute via calibrate() below; review before
# changing (principle 10: independent backtesting).
LEAGUE_FG_PCT = {
    "20_29": 0.977,
    "30_39": 0.937,
    "40_49": 0.808,
    "50_plus": 0.692,
}
# Prior strength (pseudo-attempts) per band for shrinkage.
PRIOR_N = {"20_29": 30, "30_39": 40, "40_49": 40, "50_plus": 25}

# League-average share of FG attempts falling in each band (2024-2025).
BAND_SHARE = {"20_29": 0.203, "30_39": 0.274, "40_49": 0.278, "50_plus": 0.245}

# FG attempts per team point, calibrated 2024-2025 nflverse: 2.025
# att/team-game at 22.96 pts/team-game -> 0.088. Computed over ALL 1,088
# regular-season team-games INCLUDING zero-attempt games (122 team-games had
# no FG try). The previous 0.099 used only the 966 team-games with >=1
# attempt in the attempt mean while scoring was divided across all games --
# a biased numerator/denominator mix (recomputed 2026-09-17; see
# engine/CALIBRATION_NOTES.md). Red-zone stall modulates around this base.
FG_PER_IMPLIED_PT = 0.088
# League-average red-zone TD rate; stall = 1 - rz_td_rate. Calibrated
# 2024-2025 nflverse: 2,777 TDs on 4,587 red-zone trips = 0.606.
# (The old 0.56 was an uncalibrated guess.)
LEAGUE_RZ_TD = 0.606
# Dome attempt premium: at fixed implied total, dome games see +0.24 FG
# attempts (t=2.8, 2024-2025, n=1088) -- coaches attempt longer kicks with
# no wind instead of punting. Fit in-sample; needs out-of-sample validation
# before any production use.
DOME_ATT_MULT = 1.12
# PAT opportunity, calibrated 2024-2025 nflverse (2,626 PAT attempts,
# mean 2.30 per REG team-game): pat_att = PAT_A + PAT_B * team_points,
# R^2 = 0.76. The old flat pat_rate=1.9 default undercounted PATs by
# ~0.4 attempts/game (~0.38 pts). pat_rate is kept as an explicit
# override; when None (the default) the calibrated line is used.
PAT_A = -0.642
PAT_B = 0.1282
# PAT conversion rate, 2024-2025: 2,514/2,626 = 0.957.
PAT_CONV = 0.957

# Scoring systems: points per make by band, per miss, per PAT.
SCORING = {
    "conventional_345": {  # 3 / 3 / 4 / 5 by band
        "make": {"20_29": 3.0, "30_39": 3.0, "40_49": 4.0, "50_plus": 5.0},
        "miss": 0.0, "pat": 1.0},
    "flat_three": {
        "make": {"20_29": 3.0, "30_39": 3.0, "40_49": 3.0, "50_plus": 3.0},
        "miss": 0.0, "pat": 1.0},
    "decimal_distance": {  # 0.1 pt per yard, e.g. 42-yd FG = 4.2
        "make": "distance", "miss": 0.0, "pat": 1.0},
    "miss_penalty": {  # conventional 3/4/5 with -1 per miss
        "make": {"20_29": 3.0, "30_39": 3.0, "40_49": 4.0, "50_plus": 5.0},
        "miss": -1.0, "pat": 1.0},
}

BAND_MIDPOINT = {"20_29": 24.5, "30_39": 34.5, "40_49": 44.5, "50_plus": 54.0}


def band_of(distance_yds):
    if distance_yds < 30:
        return "20_29"
    if distance_yds < 40:
        return "30_39"
    if distance_yds < 50:
        return "40_49"
    return "50_plus"


def shrunk_accuracy(kicker_makes, kicker_atts):
    """Per-band FG% shrunk toward the league prior.

    kicker_makes/atts: dicts band -> count (career or rolling). New kickers
    pass empty dicts and get the league average (principle 6).
    """
    out = {}
    for b in BANDS:
        m = float((kicker_makes or {}).get(b, 0))
        a = float((kicker_atts or {}).get(b, 0))
        out[b] = (m + LEAGUE_FG_PCT[b] * PRIOR_N[b]) / (a + PRIOR_N[b])
    return out


def weather_factor(temp_f, wind_mph, precip_prob, dome):
    """Multiplicative adjustments to (attempts, accuracy).

    Dome: no weather effect. Outdoors: wind >15mph degrades accuracy and
    suppresses long attempts; extreme cold (<25F) shortens range; heavy
    precip (>60%) slightly degrades accuracy.
    Returns (att_mult, acc_mult_by_band).
    """
    if dome:
        return 1.0, {b: 1.0 for b in BANDS}
    acc = {b: 1.0 for b in BANDS}
    att = 1.0
    if wind_mph is not None:
        if wind_mph > 20:
            w = 0.90
        elif wind_mph > 15:
            w = 0.95
        else:
            w = 1.0
        acc["50_plus"] *= w
        acc["40_49"] *= (1.0 - (1.0 - w) * 0.5)
        if wind_mph > 15:
            att *= 0.96  # coaches go for it more in wind
    if temp_f is not None and temp_f < 25:
        acc["50_plus"] *= 0.92
        att *= 0.97
    if precip_prob is not None and precip_prob > 0.6:
        for b in BANDS:
            acc[b] *= 0.97
    return att, acc


def expected_attempts(team_implied, rz_td_rate, opp_rz_td_allowed=None,
                      week=1, vegas_weight=1.0, dome=False):
    """Expected FG attempts for the team's kicker.

    Base: team_implied x FG_PER_IMPLIED_PT. Modulated by the red-zone stall
    rate relative to league average: teams that stall more (low rz_td_rate)
    kick more; elite red-zone teams kick less. Opponent red-zone defense
    blends in when available. Weeks 1-4: shrink the efficiency signal toward
    league average (principle 5) -- vegas_weight in [0,1], lower = more
    shrinkage for early weeks. Dome games get the DOME_ATT_MULT premium.
    """
    if rz_td_rate is None:
        rz_td_rate = LEAGUE_RZ_TD
    if week <= 4:
        # shrink early-season efficiency toward league average
        shrink = 0.5 + 0.125 * week  # wk1: 0.625 -> wk4: 1.0
        rz_td_rate = shrink * rz_td_rate + (1 - shrink) * LEAGUE_RZ_TD
    if opp_rz_td_allowed is not None:
        # blend: half own offense's TD rate, half opponent's allowed TD rate
        # (both are TD rates; an earlier version wrongly used the complement
        #  1 - allowed, i.e. the defense's stop rate, which dragged every
        #  blended rate toward 0.50 and inflated attempts ~13%).
        rz_td_rate = 0.5 * rz_td_rate + 0.5 * opp_rz_td_allowed
    stall = 1.0 - rz_td_rate
    league_stall = 1.0 - LEAGUE_RZ_TD
    lam = max(0.0, team_implied * FG_PER_IMPLIED_PT * (stall / league_stall))
    if dome:
        lam *= DOME_ATT_MULT
    return lam


def project_kicker(team_implied, rz_td_rate=None, opp_rz_td_allowed=None,
                   kicker_makes=None, kicker_atts=None,
                   temp_f=None, wind_mph=None, precip_prob=None, dome=False,
                   week=1, pat_rate=None,
                   scoring="conventional_345", n_sims=20000, seed=42):
    """Weekly kicker projection with error bands.

    Returns dict with expected_points, p10/p25/p50/p75/p90, tier, and the
    per-band expected makes. pat_rate: explicit PAT-attempt override; when
    None (default) uses the calibrated PAT_A + PAT_B * team_implied line.
    """
    att_mult, acc_mult = weather_factor(temp_f, wind_mph, precip_prob, dome)
    lam = expected_attempts(team_implied, rz_td_rate, opp_rz_td_allowed,
                            week=week, dome=dome) * att_mult
    acc = shrunk_accuracy(kicker_makes, kicker_atts)
    for b in BANDS:
        acc[b] = min(0.995, acc[b] * acc_mult[b])

    sc = SCORING[scoring]
    if pat_rate is None:
        pats = PAT_A + PAT_B * team_implied
    else:  # legacy explicit override, mild scaling with implied total
        pats = pat_rate * (0.7 + 0.3 * team_implied / 24.0)

    rng = random.Random(seed)
    sims = []
    for _ in range(n_sims):
        n_att = rng.poisson(lam) if hasattr(rng, "poisson") else _poisson(rng, lam)
        pts = 0.0
        for _ in range(n_att):
            r = rng.random()
            cum = 0.0
            for b in BANDS:
                cum += BAND_SHARE[b]
                if r <= cum:
                    band = b
                    break
            else:
                band = "50_plus"
            made = rng.random() < acc[band]
            if made:
                mk = sc["make"]
                pts += (BAND_MIDPOINT[band] * 0.1 if mk == "distance"
                        else mk[band])
            else:
                pts += sc["miss"]
        # PATs: binomial-ish at the calibrated conversion rate
        pat_makes = sum(1 for _ in range(_poisson(rng, pats))
                        if rng.random() < PAT_CONV)
        pts += pat_makes * sc["pat"]
        sims.append(pts)

    sims.sort()
    def pct(q):
        return sims[min(n_sims - 1, int(q * n_sims))]
    exp = sum(sims) / n_sims
    return {
        "expected_points": round(exp, 2),
        "p10": round(pct(0.10), 1), "p25": round(pct(0.25), 1),
        "p50": round(pct(0.50), 1), "p75": round(pct(0.75), 1),
        "p90": round(pct(0.90), 1),
        "prob_top_tier": round(sum(1 for s in sims if s >= 12) / n_sims, 3),
        "expected_attempts": round(lam, 2),
        "scoring": scoring,
        "inputs": {"team_implied": team_implied, "rz_td_rate": rz_td_rate,
                   "week": week, "dome": dome},
    }


def _poisson(rng, lam):
    # Knuth's algorithm (random.Random has no poisson)
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def tier_of(expected_points):
    """Kicker tiers from expected points (principle 9)."""
    if expected_points >= 10.5:
        return "Tier 1 (elite)"
    if expected_points >= 9.0:
        return "Tier 2 (strong)"
    if expected_points >= 7.5:
        return "Tier 3 (solid)"
    if expected_points >= 6.0:
        return "Tier 4 (streamable)"
    return "Tier 5 (fade)"


def calibrate(pbp_parquet_paths, schedules_parquet=None):
    """Recompute LEAGUE_FG_PCT, BAND_SHARE, FG_PER_IMPLIED_PT from nflverse.

    The opportunity coefficient is computed over ALL team-games including
    zero-attempt games -- never condition the attempt mean on >=1 attempt
    while dividing by all games (that mix biased the old 0.099 upward;
    966 of 1088 REG team-games in 2024-2025 had an attempt, and the true
    all-games rate is 0.088, not 0.099).

    Prints the calibrated constants; does not overwrite the module defaults
    (review before adopting -- principle 10: independent backtesting).
    """
    import polars as pl
    fg = []
    for p in pbp_parquet_paths:
        df = pl.read_parquet(
            p, columns=["field_goal_attempt", "kick_distance",
                        "field_goal_result", "posteam", "week", "season"])
        fg.append(df.filter(pl.col("field_goal_attempt") == 1))
    fg = pl.concat(fg)
    fg = fg.with_columns(pl.col("kick_distance").map_elements(
        band_of, return_dtype=pl.String).alias("band"))
    print("FG% by band:")
    for b in BANDS:
        sub = fg.filter(pl.col("band") == b)
        n = len(sub)
        pct = (sub.filter(pl.col("field_goal_result") == "made").height / n
               if n else float("nan"))
        print(f"  {b}: {pct:.3f} (n={n})")
    print("Band share:")
    tot = len(fg)
    for b in BANDS:
        print(f"  {b}: {fg.filter(pl.col('band') == b).height / tot:.3f}")
    if schedules_parquet:
        seasons = sorted({int(str(p).split("_")[-1].split(".")[0])
                          for p in pbp_parquet_paths
                          if str(p).split("_")[-1].split(".")[0].isdigit()})
        att_tg = fg.group_by(["season", "week", "posteam"]).agg(
            pl.len().alias("att"))
        sched = pl.read_parquet(schedules_parquet).filter(
            pl.col("season").is_in(seasons) & (pl.col("game_type") == "REG"))
        tg = pl.concat([
            sched.select(["season", "week",
                          pl.col("home_team").alias("team"),
                          pl.col("home_score").alias("pts")]),
            sched.select(["season", "week",
                          pl.col("away_team").alias("team"),
                          pl.col("away_score").alias("pts")]),
        ]).filter(pl.col("pts").is_not_null())
        tg = tg.join(att_tg, left_on=["season", "week", "team"],
                     right_on=["season", "week", "posteam"],
                     how="left").with_columns(pl.col("att").fill_null(0))
        nz = tg.filter(pl.col("att") > 0)
        print(f"team-games: {len(tg)} total, {len(nz)} with >=1 attempt")
        print(f"  all-games: att={tg['att'].mean():.4f} "
              f"pts={tg['pts'].mean():.4f} "
              f"FG_PER_IMPLIED_PT={tg['att'].mean()/tg['pts'].mean():.4f}")
        print(f"  (for reference) attempt-conditional: "
              f"{nz['att'].mean()/nz['pts'].mean():.4f} -- DO NOT USE")


if __name__ == "__main__":
    # Smoke test: league-average kicker, 24 implied, neutral conditions.
    r = project_kicker(team_implied=24.0, week=5, n_sims=5000)
    print(json.dumps(r, indent=1) if (json := __import__("json")) else r)
    print("tier:", tier_of(r["expected_points"]))
