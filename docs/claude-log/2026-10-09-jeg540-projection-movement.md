# Weekly projection movement and error (Sleeper weekly projections 2018-2025, full PPR)

Produced by `tools/projection_movement.py` (JEG-540). Players at or above the 12-team rostered line by that week's projection, followed while they keep being projected.

## How far a projection moves over h weeks (robust sd of the relative change)

| Position | h=1 | h=2 | h=3 | h=4 | h=5 | h=6 | h=7 | h=8 | Matchup noise (sd) | Level drift per week (sd) | Stand-in drift per week (spec) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB | 7% | 7% | 8% | 8% | 8% | 8% | 9% | 9% | 4.5% | 2.3% | 2.3% |
| RB | 16% | 20% | 22% | 25% | 28% | 29% | 30% | 32% | 9.5% | 10.4% | 10.4% |
| WR | 12% | 14% | 16% | 18% | 19% | 21% | 22% | 23% | 7.2% | 7.3% | 7.3% |
| TE | 12% | 14% | 16% | 17% | 19% | 20% | 20% | 23% | 6.6% | 7.2% | 7.2% |

## Weekly projection error against actual points (projected rostered players who played)

Matched 22,642 of 23,640 eligible player-weeks to nflverse actuals.

| Position | sd of (actual - projection) / projection | Mean bias | Player-weeks |
| --- | --- | --- | --- |
| QB | 38% | -16.6% | 2,953 |
| RB | 82% | +3.5% | 7,213 |
| WR | 72% | -0.9% | 9,635 |
| TE | 70% | -0.2% | 2,841 |

## Bench share at 12-team full PPR, Week 5, defaults (season objective)

| Uncertainty | sigma QB / RB / WR / TE | Bench share, chance of starting (approved) | Bench share, with the upside | RB starter/bench price, approved | with the upside |
| --- | --- | --- | --- | --- | --- |
| stand-in sigma (current spec) | 15% / 28% / 22% / 20% | 8.9% | 11.7% | 1.66x | 1.26x |
| measured drift (Sleeper weekly projections) | 15% / 28% / 22% / 20% | 8.9% | 11.7% | 1.66x | 1.26x |
