# Expected-starts parameters, derived from repo data

Content week 5, ppr scoring, 12 teams. Schema `lineup-parameters/1`. Produced by `pipelines/derive_lineup_parameters.py`.

## Recommended parameters

| Position | m (healthy starters) | 95% interval | team games | m, 2024-2025 only | m, all rostered | sigma now (spread) | sigma drift (to mid-window) | sigma used | sigma floor (ppg) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB | 11.0% | 9.8% to 12.3% | 2,319 | 9.9% | 13.6% | 14.0% | 11.6% | 18.2% | 0.69 |
| RB | 15.3% | 14.4% to 16.2% | 5,816 | 10.0% | 16.4% | 11.1% | 27.9% | 30.0% | 0.89 |
| WR | 11.7% | 11.0% to 12.4% | 8,128 | 13.0% | 13.7% | 12.3% | 28.2% | 30.8% | 1.01 |
| TE | 14.4% | 13.0% to 15.8% | 2,331 | 15.9% | 14.8% | 8.1% | 35.3% | 36.2% | 0.64 |

m source: healthy starters, 2015-2025 (nflverse), selection weeks 1-5 and 1-9, measured to the season's last week minus one.

## Missed-game hazard of healthy starters by season (nflverse, 2015-2025)

| Season | Selected on | Measured | QB | RB | WR | TE |
| --- | --- | --- | --- | --- | --- | --- |
| 2015 | weeks 1-5 | weeks 6-16 | 10.6% | 22.0% | 10.7% | 12.2% |
| 2015 | weeks 1-9 | weeks 10-16 | 13.6% | 18.7% | 9.9% | 14.8% |
| 2016 | weeks 1-5 | weeks 6-16 | 1.6% | 20.3% | 7.5% | 11.4% |
| 2016 | weeks 1-9 | weeks 10-16 | 1.3% | 11.5% | 7.6% | 17.1% |
| 2017 | weeks 1-5 | weeks 6-16 | 17.1% | 11.1% | 12.6% | 9.8% |
| 2017 | weeks 1-9 | weeks 10-16 | 6.2% | 11.8% | 12.6% | 2.5% |
| 2018 | weeks 1-5 | weeks 6-16 | 6.6% | 13.4% | 13.8% | 8.1% |
| 2018 | weeks 1-9 | weeks 10-16 | 12.2% | 14.0% | 14.7% | 14.8% |
| 2019 | weeks 1-5 | weeks 6-16 | 9.9% | 16.2% | 14.4% | 29.5% |
| 2019 | weeks 1-9 | weeks 10-16 | 9.1% | 11.8% | 12.0% | 16.7% |
| 2020 | weeks 1-5 | weeks 6-16 | 13.0% | 19.6% | 11.1% | 12.1% |
| 2020 | weeks 1-9 | weeks 10-16 | 6.2% | 18.1% | 6.8% | 7.5% |
| 2021 | weeks 1-5 | weeks 6-17 | 16.7% | 21.8% | 14.7% | 12.9% |
| 2021 | weeks 1-9 | weeks 10-17 | 6.6% | 23.1% | 11.4% | 13.2% |
| 2022 | weeks 1-5 | weeks 6-17 | 15.4% | 19.2% | 11.6% | 17.6% |
| 2022 | weeks 1-9 | weeks 10-17 | 16.1% | 11.6% | 11.3% | 20.9% |
| 2023 | weeks 1-5 | weeks 6-17 | 20.3% | 12.3% | 10.7% | 15.2% |
| 2023 | weeks 1-9 | weeks 10-17 | 6.7% | 14.3% | 9.1% | 14.6% |
| 2024 | weeks 1-5 | weeks 6-17 | 11.3% | 13.4% | 20.2% | 11.3% |
| 2024 | weeks 1-9 | weeks 10-17 | 2.3% | 11.2% | 8.7% | 11.5% |
| 2025 | weeks 1-5 | weeks 6-17 | 15.8% | 9.9% | 11.1% | 19.4% |
| 2025 | weeks 1-9 | weeks 10-17 | 13.5% | 6.6% | 8.9% | 21.7% |

Bye share of remaining team-weeks: 7.2% (30 of 32 teams have a bye in weeks 6-18, 13 weeks).

## Missed-game hazard by cell, 2024-2025 Supabase export (rate of team games with no stat line)

| Season | Selected on | Measured | QB starters | RB starters | WR starters | TE starters | QB rostered | RB rostered | WR rostered | TE rostered |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024 | weeks 1-5 | weeks 6-17 | 11.3% | 12.5% | 20.6% | 11.3% | 15.5% | 11.7% | 16.7% | 10.3% |
| 2024 | weeks 1-9 | weeks 10-17 | 2.3% | 9.9% | 8.7% | 11.5% | 15.0% | 10.9% | 9.6% | 14.9% |
| 2025 | weeks 1-5 | weeks 6-17 | 11.2% | 9.9% | 11.1% | 19.4% | 19.3% | 14.2% | 17.2% | 17.6% |
| 2025 | weeks 1-9 | weeks 10-17 | 13.5% | 6.6% | 8.9% | 21.7% | 16.2% | 11.4% | 15.4% | 18.9% |

Pooled, with the split into temporary absences (the player returned) and season-ending ones:

| Position | Group | Team games | Missed | Rate | Temporary | Season-ending |
| --- | --- | --- | --- | --- | --- | --- |
| QB | starters | 443 | 44 | 9.9% | 0.2% | 9.7% |
| QB | bench | 336 | 86 | 25.6% | 4.8% | 20.8% |
| QB | rostered | 779 | 130 | 16.7% | 2.2% | 14.5% |
| RB | starters | 1120 | 112 | 10.0% | 3.1% | 6.9% |
| RB | bench | 886 | 133 | 15.0% | 6.7% | 8.4% |
| RB | rostered | 2006 | 245 | 12.2% | 4.7% | 7.5% |
| WR | starters | 1559 | 203 | 13.0% | 5.6% | 7.4% |
| WR | bench | 1112 | 202 | 18.2% | 7.0% | 11.2% |
| WR | rostered | 2671 | 405 | 15.2% | 6.2% | 8.9% |
| TE | starters | 446 | 71 | 15.9% | 3.8% | 12.1% |
| TE | bench | 333 | 47 | 14.1% | 6.0% | 8.1% |
| TE | rostered | 779 | 118 | 15.1% | 4.7% | 10.4% |

## Cross-source spread this week (sample sd over mean of ESPN, CBS rest of season, Razzball)

| Position | Bucket | Ranks | Players | Median relative | Mean relative | Median absolute (ppg) | Mean ppg |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QB | top half of starters | 1-6 | 6 | 14.3% | 15.3% | 2.86 | 20.3 |
| QB | lower half of starters | 7-12 | 6 | 12.2% | 13.8% | 2.28 | 18.7 |
| QB | bench | 13-21 | 9 | 14.0% | 15.2% | 2.41 | 16.8 |
| QB | below the roster | 22-61 | 40 | 72.5% | 62.0% | 0.48 | 3.6 |
| RB | top half of starters | 1-15 | 15 | 8.5% | 9.0% | 1.59 | 17.7 |
| RB | lower half of starters | 16-30 | 15 | 10.5% | 12.4% | 1.05 | 11.6 |
| RB | bench | 31-54 | 24 | 17.9% | 24.2% | 0.94 | 5.9 |
| RB | below the roster | 55-91 | 37 | 54.8% | 61.1% | 0.78 | 1.8 |
| WR | top half of starters | 1-21 | 21 | 6.7% | 7.0% | 1.08 | 16.1 |
| WR | lower half of starters | 22-42 | 21 | 8.3% | 9.9% | 0.89 | 11.1 |
| WR | bench | 43-72 | 30 | 14.9% | 17.8% | 1.18 | 7.5 |
| WR | below the roster | 73-136 | 64 | 37.3% | 46.2% | 0.79 | 2.7 |
| TE | top half of starters | 1-6 | 6 | 8.4% | 8.2% | 1.23 | 13.8 |
| TE | lower half of starters | 7-12 | 6 | 10.2% | 10.8% | 1.14 | 10.7 |
| TE | bench | 13-21 | 9 | 7.7% | 14.4% | 0.64 | 8.7 |
| TE | below the roster | 22-97 | 76 | 26.8% | 35.3% | 0.63 | 2.9 |

Players with an unavailable Sleeper status are excluded above. Their median relative spread: QB 14.7%, RB 33.7%, WR 41.0%, TE 55.2%. That spread is absence (ESPN's per-game number is per team game), not disagreement.

## Week-to-week movement of the per-game projections (relative, demeaned, robust sd)

| Source | Weeks | Position | Players | Median shift | Robust sd |
| --- | --- | --- | --- | --- | --- |
| espn | 2 to 3 | QB | 30 | -0.7% | 2.9% |
| espn | 3 to 4 | QB | 31 | -12.5% | 4.5% |
| espn | 4 to 5 | QB | 33 | 15.2% | 4.1% |
| espn | 2 to 3 | RB | 56 | -1.1% | 10.6% |
| espn | 3 to 4 | RB | 51 | -15.4% | 9.1% |
| espn | 4 to 5 | RB | 49 | 14.7% | 9.7% |
| espn | 2 to 3 | WR | 90 | -0.3% | 10.5% |
| espn | 3 to 4 | WR | 91 | -12.9% | 8.6% |
| espn | 4 to 5 | WR | 80 | 14.7% | 10.9% |
| espn | 2 to 3 | TE | 33 | -4.0% | 7.7% |
| espn | 3 to 4 | TE | 34 | -13.6% | 11.4% |
| espn | 4 to 5 | TE | 32 | 13.4% | 12.7% |
| razzball | 3 to 4 | QB | 33 | -5.4% | 6.9% |
| razzball | 4 to 5 | QB | 31 | -1.2% | 6.0% |
| razzball | 3 to 4 | RB | 54 | -1.1% | 13.0% |
| razzball | 4 to 5 | RB | 55 | 0.5% | 12.4% |
| razzball | 3 to 4 | WR | 80 | -5.7% | 16.1% |
| razzball | 4 to 5 | WR | 80 | 0.0% | 12.0% |
| razzball | 3 to 4 | TE | 32 | -11.9% | 20.0% |
| razzball | 4 to 5 | TE | 30 | 0.6% | 17.7% |
| cbsros | 4 to 5 | QB | 32 | -0.8% | 2.9% |
| cbsros | 4 to 5 | RB | 59 | -2.3% | 10.9% |
| cbsros | 4 to 5 | WR | 90 | 0.1% | 8.2% |
| cbsros | 4 to 5 | TE | 39 | -4.8% | 13.6% |

The ESPN median shifts of about 20% between weeks 3, 4 and 5 are the GAP-GAMES-REMAINING-STALE denominator, not projection changes; demeaning removes them.

## Realized weekly noise of starters (sd over mean of weekly points; 2015-2025 when the history file is present)

| Position | Median | Players |
| --- | --- | --- |
| QB | 38% | 132 |
| RB | 52% | 330 |
| WR | 55% | 462 |
| TE | 59% | 132 |

Weekly noise is what a manager faces on Sunday. It is several times the level uncertainty above and is not what sigma in the spec measures (ES-5).
