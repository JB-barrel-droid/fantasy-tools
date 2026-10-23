# Source accuracy backtest (preliminary)

Script: `tools/research/source_accuracy_backtest.py`, run 2026-10-23.
Scoring: ppr. Weeks: [2, 3, 4, 5, 6]. Total player-weeks: 1655.

## Caveat

This compares rest-of-season per-game projections against single-week actual
points. ROS projections are not week-ahead projections. The error is inflated
by bye weeks, injuries, and game-to-game variance that week-ahead projections
partially account for. This is a directional check, not a definitive ranking.

## Per-source accuracy

| Source | N | MAE | RMSE | Bias | MAE 95% CI |
|---|---|---|---|---|---|
| espn | 1425 | 4.68 | 6.40 | -0.90 | [4.46, 4.91] |
| cbsros | 703 | 5.05 | 6.66 | -0.71 | [4.74, 5.36] |
| razzball | 1171 | 4.50 | 6.30 | -1.27 | [4.22, 4.75] |
| espn_weekly | 1600 | 4.36 | 5.96 | -0.16 | [4.17, 4.56] |
| equal_mean | 1122 | 4.61 | 6.28 | -1.10 | [4.37, 4.87] |
| median | 1122 | 4.61 | 6.30 | -1.13 | [4.37, 4.87] |
| inverse_mae_weighted | 1122 | 4.61 | 6.28 | -1.11 | [4.38, 4.87] |

## By position (equal-weight mean)

| Pos | N | MAE | RMSE | Bias |
|---|---|---|---|---|
| QB | 128 | 5.66 | 7.19 | -0.66 |
| RB | 294 | 4.62 | 6.29 | -1.17 |
| WR | 445 | 4.57 | 6.35 | -1.22 |
| TE | 255 | 4.13 | 5.59 | -1.05 |
