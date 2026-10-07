# Vegas Implied Totals vs Actual Fantasy Points — Backtest

**Data:** 1,090 team-games (545 REG-season games, 2024–2025) with spread + total, joined to 36,700 player-week stat rows. 2026 excluded — only one game played at load time. Implied totals use the nflverse convention (positive spread = home favored): home = total/2 + spread/2, away = total/2 − spread/2. Team fantasy = sum of rostered offensive players' PPR points (no DST).

## Headline numbers

- **Scale bridge:** actual team FP ≈ 40.9 + 1.84 × (points scored), r = 0.77. Every Vegas-implied point is worth ~1.8 fantasy points; ~41 FP of yardage accrues regardless of score.
- **Implied total → actual team FP:** r = **0.41** (R² ≈ 0.17), **MAE 17.1 FP** vs 18.7 for a naive always-predict-the-mean baseline, RMSE 21.6. Mean team FP is 83 (SD 23.5), so typical error is ~20% of the mean.
- **Hit rates:** within ±5 FP 19% · ±10 FP 37% · ±15 FP 53%.

## Per-season

| Season | n (team-games) | r | MAE | Baseline MAE |
|---|---|---|---|---|
| 2024 | 544 | 0.40 | 16.8 | 18.4 |
| 2025 | 544 | 0.43 | 17.4 | 18.9 |
| All | 1,090 | 0.41 | 17.1 | 18.7 |

Stable across both seasons — the relationship is real, not a one-year artifact.

## Bonus: does beating the implied total predict covering?

Yes, emphatically — with a caveat (below). Excluding pushes (baseline cover = 50.0%):

| FP edge vs implied | Cover rate | n |
|---|---|---|
| > 0 | **62.5%** | 558 |
| ≤ 0 | 36.5% | 520 |
| > +10 | **68.3%** | 347 |
| < −10 | 31.0% | 329 |

## Verdict

**Implied totals are a solid foundation, but a modest one.** They genuinely move the needle over nothing (MAE 17.1 vs 18.7, stable correlation both seasons), and the accounting is internally consistent: fantasy points track points scored at r = 0.77, and the cover-rate split confirms the fantasy lens captures the same signal as the scoreboard.

Two honest limits:

1. **This backtest is descriptive, not predictive.** It shows implied totals *describe* team fantasy output after the fact. The product's edge has to come from the *pre-game* disagreement — props-implied FP vs ECR — predicting which side of the edge a team/player lands on. That is the backtest still to run once the props collector is live.
2. **Team-level is noisy.** ±17 FP on an 83-FP mean is coarse. Player-level props should be sharper per unit of signal (a WR's receiving-yards prop maps almost directly to FP), but noisier per observation. The disagreement engine's thresholds should be calibrated against player-level error, not these team numbers.

Bottom line: the Vegas-to-fantasy translation rests on a real, stable relationship. Build the player-level disagreement layer on top of it — that's where the alpha lives.
