# JEG-525 open items: measured reports (Week 5 build, 2026-10-09)

Produced by the tools named in each section; `output/` is not committed, so the reports are kept here. Spec text: docs/methodology.md ES-1 note, ES-12, ES-13. Agenda: MR-22, MR-25, MR-26, MR-27.

## Running back missed games: structural or variance? (JEG-525 item d)

Produced by `tools/rb_hazard_trend.py` on `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`, the same healthy-starter selection as `derive_lineup_parameters.py` (ES-1). Intervals are player-cluster bootstraps (2000 draws).

### Per season, healthy starters (both selection windows pooled)

| Season | QB | RB | WR | TE |
| --- | --- | --- | --- | --- |
| 2015 | 11.8% (4%-21%) | 20.7% (13%-29%) | 10.4% (6%-15%) | 13.2% (6%-21%) |
| 2016 | 1.5% (0%-3%) | 16.8% (10%-24%) | 7.5% (4%-11%) | 13.7% (6%-23%) |
| 2017 | 12.8% (4%-25%) | 11.4% (7%-17%) | 12.6% (8%-18%) | 6.9% (3%-12%) |
| 2018 | 8.8% (2%-18%) | 13.7% (9%-20%) | 14.2% (9%-20%) | 10.8% (4%-19%) |
| 2019 | 9.6% (2%-20%) | 14.5% (10%-20%) | 13.5% (9%-18%) | 24.5% (12%-38%) |
| 2020 | 10.3% (1%-23%) | 19.0% (14%-25%) | 9.4% (6%-13%) | 10.3% (5%-17%) |
| 2021 | 12.6% (6%-20%) | 22.3% (17%-28%) | 13.4% (9%-18%) | 13.0% (6%-21%) |
| 2022 | 15.7% (7%-26%) | 16.1% (10%-23%) | 11.5% (7%-16%) | 18.9% (11%-28%) |
| 2023 | 14.8% (5%-27%) | 13.1% (9%-18%) | 10.1% (7%-14%) | 14.9% (8%-23%) |
| 2024 | 7.7% (1%-18%) | 12.5% (9%-17%) | 15.6% (10%-21%) | 11.4% (5%-19%) |
| 2025 | 14.9% (6%-25%) | 8.5% (4%-14%) | 10.2% (7%-14%) | 20.4% (8%-33%) |

### Tests

| Position | Pooled (cluster 95%) | Trend per season (95%) | Trend permutation p | Over-dispersion Q (df), p | I-squared | 2015-2021 | 2022-2025 | Difference (95%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB | 11.0% (8.3%-13.9%) | +0.57 pts (-0.25 to +1.39) | 0.15 | 40.6 (10), 0.000 | 75% | 9.7% | 13.3% | +3.6 pts (-2.3 to +9.6) |
| RB | 15.3% (13.5%-17.1%) | -0.56 pts (-1.12 to +0.04) | 0.17 | 21.7 (10), 0.017 | 54% | 17.0% | 12.6% | -4.4 pts (-7.9 to -0.9) |
| WR | 11.7% (10.3%-13.0%) | +0.16 pts (-0.24 to +0.60) | 0.52 | 12.4 (10), 0.260 | 19% | 11.6% | 11.8% | +0.2 pts (-2.4 to +3.0) |
| TE | 14.4% (11.8%-17.1%) | +0.51 pts (-0.38 to +1.37) | 0.31 | 13.2 (10), 0.214 | 24% | 13.2% | 16.4% | +3.2 pts (-2.5 to +9.1) |

### Candidate m_RB and the bench-share effect (12-team full PPR, Week 5)

| Candidate | m_RB | Bench tier (all positions) | RB bench tier | Pie on fill-in parts | RB starter/bench price |
| --- | --- | --- | --- | --- | --- |
| all seasons 2015-2025 | 15.3% | 8.65% | 9.25% | 5.31% | 1.61x |
| recency weight, half-life 5 seasons | 14.4% | 8.62% | 9.19% | 5.24% | 1.63x |
| recency weight, half-life 3 seasons | 13.8% | 8.60% | 9.14% | 5.18% | 1.64x |
| 2022-2025 | 12.6% | 8.56% | 9.04% | 5.06% | 1.67x |
| 2024-2025 | 10.5% | 8.50% | 8.89% | 4.85% | 1.72x |

## Backup running back when the lead back misses (nflverse 2015-2025, full PPR)

Team-seasons: 312. Backup games with the lead back playing: 1489; with the lead back out: 242.

- Backup points per game, lead back playing: 7.2
- Backup points per game, lead back out: 12.8
- Median jump per backup (both states observed, 102 backups): +4.0
- Share of those backups above the 12-team starter line (RB31, mean 10.8) when the lead back is out: 54%
- Share above the waiver line (RB55, mean 6.3) with the lead back playing: 51%
- Behind a top-12 lead back (33 backups): 6.9 -> 13.4 points per game; above the starter line when the lead back is out: 55%

## League week inputs: effect on the expected-starts value (12-team full PPR, Week 5)

Produced by `tools/season_window_effect.py`. Playoff-week hazard of healthy starters (2015-2025): QB 15.6%, RB 19.7%, WR 14.7%, TE 18.6%.

| Objective window | Bye share | m_RB | sigma_RB | Bench tier | Pie on fill-in parts | RB starter/bench price |
| --- | --- | --- | --- | --- | --- | --- |
| today's spec: weeks 6-18 | 7.2% | 15.3% | 30.0% | 8.65% | 5.31% | 1.61x |
| season: weeks 6-17 (regular season and playoffs) | 7.8% | 15.3% | 29.0% | 8.65% | 5.43% | 1.61x |
| regular season: weeks 6-14 | 10.4% | 15.3% | 25.7% | 8.71% | 5.89% | 1.60x |
| playoffs: weeks 15-17, per-game hazard | 0.0% | 15.3% | 38.0% | 8.47% | 3.79% | 1.65x |
| playoffs: weeks 15-17, hazard measured in the playoff weeks | 0.0% | 19.7% | 38.0% | 8.71% | 4.71% | 1.56x |

## Post-bye rookie bump (nflverse 2016-2025, full PPR, RB/WR/TE with 3+ games each side of the bye)

| Group | Rookies | Veterans | Rookie change after bye | Veteran change | Bump (difference) | 95% interval |
| --- | --- | --- | --- | --- | --- | --- |
| all | 464 | 2356 | +0.85 | -0.19 | +1.04 | +0.67 to +1.40 |
| RB | 150 | 684 | +1.15 | -0.07 | +1.22 | +0.53 to +1.96 |
| WR | 230 | 1084 | +0.90 | -0.42 | +1.32 | +0.79 to +1.84 |
| TE | 84 | 588 | +0.22 | +0.12 | +0.09 | -0.57 to +0.80 |
| pre-bye 0-4 points per game | 213 | 687 | +1.51 | +1.13 | +0.39 | -0.09 to +0.88 |
| pre-bye 4-8 points per game | 128 | 609 | +0.83 | +0.27 | +0.57 | -0.10 to +1.21 |
| pre-bye 8+ points per game | 123 | 1055 | -0.27 | -1.32 | +1.06 | +0.30 to +1.85 |
