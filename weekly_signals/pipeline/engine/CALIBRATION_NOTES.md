# Kicker model calibration notes

All constants below are calibrated on our own 2024–2025 nflverse pull
(1,088 regular-season team-games, 2,306 FG attempts, 2,626 PAT attempts).
No Project Upright data is used anywhere; only its methodological logic.

## Constants (engine/kicker_model.py)

| Constant | Value | Basis |
|---|---|---|
| `FG_PER_IMPLIED_PT` | 0.088 | 2.025 att / 22.96 pts per team-game, ALL team-games |
| `LEAGUE_FG_PCT` | .977 / .937 / .808 / .692 | by distance band (n=469/632/640/565) |
| `BAND_SHARE` | .203 / .274 / .278 / .245 | attempt share by band |
| `LEAGUE_RZ_TD` | 0.606 | 2,777 TDs on 4,587 red-zone trips |
| `PAT_A` / `PAT_B` | −0.642 / 0.1282 | pat_att = A + B·team_pts, R²=0.76 |
| `PAT_CONV` | 0.957 | 2,514 makes / 2,626 attempts |
| `DOME_ATT_MULT` | 1.12 | +0.24 att/game in domes at fixed implied (t=2.8); in-sample |

## Bug history (fixed 2026-09-17)

1. **FG_PER_IMPLIED_PT numerator/denominator mix** — the old 0.099 divided
   the attempt mean over only the 966 team-games with ≥1 attempt by the
   point mean over all 1,088 games. Recomputed over all games: 0.088.
   `calibrate()` now prints both and labels the conditional one DO NOT USE.
2. **Red-zone blend used the defensive stop rate** — `expected_attempts`
   blended `0.5·own + 0.5·(1 − opp_allowed)`, dragging every matchup rate
   toward 0.50 and inflating attempts ~13%. Now blends the two TD rates.
3. **LEAGUE_RZ_TD was an uncalibrated 0.56** — true 2024–2025 rate is 0.606.
4. **Analog/PAT table dropped PATs in zero-FG-attempt games** —
   `kicker_history._kicker_game_stats` joined PATs off the FG table (left
   join), zeroing ~440 PAT attempts. Now a full outer join. Same bug class
   as (1): never condition a counting join on ≥1 attempt.
5. **Flat PAT default** — `pat_rate=1.9` undercounted PATs ~0.4/game and
   barely scaled with implied total. Replaced with the calibrated line
   (explicit `pat_rate` still overrides).

## Backtest (engine/backtest_kicker.py, 2024–2025, n=1,088)

Inputs strictly pregame-knowable: closing spread/total → implied,
dome, recorded temp/wind (forecast proxy), season-to-date red-zone rates
through the prior week, team's primary kicker through the prior week with
prior band accuracy (2024 season for 2025 games; 2024-to-date for 2024).

| | bias | MAE | RMSE | corr |
|---|---|---|---|---|
| model | −0.00 | 3.81 | 4.82 | 0.15 |
| naive (league mean) | 0.00 | 3.79 | 4.74 | — |
| implied-only line (in-sample) | −0.00 | 3.72 | 4.67 | 0.16 |

Honest read: the model is unbiased and ties the naive mean on MAE, but
does not beat it — weekly kicker scoring is dominated by binomial noise
(std 4.74 on mean 8.51), so the predictable ceiling is low. Where the model
adds value is cross-sectional: mean weekly rank correlation (Spearman) with
actuals is 0.174 vs 0.156 for the implied-only line (model better in 20/36
weeks), from kicker accuracy priors, red-zone matchup, weather, and dome.

The naive baseline is the in-sample mean (bias 0 by construction) — not a
real forecasting baseline. DOME_ATT_MULT is fit in-sample; the whole model
needs an out-of-sample season before any production use.

## Open items

- Out-of-sample validation on 2026 once the season completes.
- Weather coefficients (wind/cold/precip) are still rule-of-thumb
  thresholds, not fitted — enough historical temp/wind exists in the
  team-game table to fit them.
- 50+ band accuracy prior (PRIOR_N=25) is the noisiest; consider
  kicker-specific long-range priors with more shrinkage.
- Implied-vs-actual denominator: RTO slope of att on implied is 0.0889 vs
  the adopted 0.0882 — immaterial; revisit if the gap grows.
