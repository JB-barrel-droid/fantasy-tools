# JEG-1310: CBS rest-of-season against the other projections

Research only. No math, parser, leg, resolutions, fixture or Supabase change.
Follows JEG-1171 (PR #1113). Checked 2026-10-29 on `main` at `a33c80b` plus
later merges up to `b161eb7`, week-8 build (CBS ROS 2026-10-29, ESPN
2026-10-28, Razzball 2026-10-27). All three are rest of season; no weekly
data is compared with them (Jeremy, 2026-10-28: "do not blend weekly data
with ROS data, ever.").

## Decision

Jeremy, 2026-10-29, answering the three options below: "Leave as is". So
there is no rescore and no weight change for CBS rest of season, and no value
changes. Jalen Coker's low CBS number is CBS's own projection (also JEG-1287).
No entry was added to `data/source-divergence-resolutions.json`, so the
divergence warn can come back in later weeks.

## Answer (as researched)

**Recommendation at the time: Option A, then record the rest as CBS's opinion.** Rescore
CBS from its own published stat line on the shared basis, and log what
disagreement is left in `data/source-divergence-resolutions.json` as genuine
CBS opinion. Don't down-weight or drop CBS.

- **The cause is mostly scoring, and it is now proven per player for week 8.**
  JEG-1171 could only infer it from the 09-30 snapshot. Supabase keeps CBS's
  stat line (`raw_stats`) for every daily snapshot, so week 8 can be rescored
  player by player. CBS's printed points are about 6-point passing TDs, and
  they sit a fixed 3 to 4 points per yardage category below what CBS's own
  stat line scores. That gap is consistent with rounding yardage down to
  whole points each game. Parsing is clean: JEG-1171 traced it end to end.
- **The rescore barely moves DDF Value (projections).** Each source is priced
  within its own position (waiver line, pies), so a position-wide scoring
  bias mostly cancels out. Mean move in the top 100 is 0.2 to 0.4 points. The
  biggest moves are Bucky Irving +2.7 and Joe Burrow −1.4 (12 teams, full PPR).
- **What does move values is CBS's player-level opinion.** Examples are
  Jalen Coker, David Montgomery, Chris Olave, Davante Adams and Jonathan
  Taylor. Rescoring doesn't touch these, because they are CBS's numbers.
  Jeremy confirmed Coker's on CBS's page (JEG-1287). After the rescore, CBS
  disagrees about as much as Razzball does (41 to 45% outliers against
  Razzball's 43%).

## How far off CBS is, by position and week

Half PPR. Players that ESPN and Razzball together put at 5+ points a game.
"CBS / others" is the median of CBS ÷ the mean of ESPN and Razzball. The last
column is the yardstick: how often ESPN and Razzball are 25%+ apart from each
other.

| Week (CBS date) | Pos | n | CBS − others, ppg | CBS / others | CBS 25%+ off | ESPN vs Razzball 25%+ off |
| -- | -- | -- | -- | -- | -- | -- |
| 4 (10-02) | QB | 32 | +4.27 | 1.29 | 63% | 19% |
| | RB | 46 | +0.01 | 1.00 | 17% | 11% |
| | WR | 63 | +0.83 | 1.11 | 16% | 11% |
| | TE | 20 | +1.88 | 1.29 | 60% | 15% |
| 5 (10-12) | QB | 29 | +2.75 | 1.18 | 28% | 41% |
| | RB | 48 | −1.20 | 0.88 | 31% | 23% |
| | WR | 68 | +0.25 | 1.03 | 12% | 18% |
| | TE | 28 | +0.53 | 1.08 | 21% | 14% |
| 6 (10-19) | QB | 28 | +2.92 | 1.18 | 21% | 50% |
| | RB | 49 | −1.45 | 0.86 | 24% | 31% |
| | WR | 65 | +0.13 | 1.01 | 9% | 28% |
| | TE | 29 | +0.12 | 1.02 | 10% | 17% |
| 7 (10-26) | QB | 32 | +2.81 | 1.17 | 19% | 53% |
| | RB | 54 | −1.07 | 0.88 | 19% | 11% |
| | WR | 68 | −0.23 | 0.97 | 10% | 21% |
| | TE | 29 | −0.09 | 0.99 | 10% | 17% |
| 8 (10-29) | QB | 32 | +2.55 | 1.16 | 34% | 47% |
| | RB | 53 | −1.12 | 0.90 | 9% | 17% |
| | WR | 68 | −0.16 | 0.98 | 7% | 19% |
| | TE | 31 | +0.05 | 1.01 | 13% | 23% |
| **8, CBS rescored (A)** | QB | 32 | +0.12 | 1.01 | 3% | 47% |
| | RB | 53 | −0.40 | 0.96 | 15% | 17% |
| | WR | 69 | +0.21 | 1.03 | 10% | 19% |
| | TE | 31 | +0.41 | 1.06 | 19% | 23% |

What the table says:

- CBS QBs run 2.5 to 4.3 points a game high every week. After the rescore,
  they land on the ESPN and Razzball mean.
- CBS RBs run about 1.1 to 1.5 low from week 5 on. The rescore cuts that to
  0.4.
- Week 4 WR and TE were high too. That week predates the JEG-535 per-game fix
  and isn't investigated here.
- ESPN and Razzball disagree a lot on QBs themselves (47% of QBs 25%+ apart
  in week 8, ESPN +3.8 ppg). Part of that is ESPN's leg leaving out
  interceptions and fumbles (`pipelines/fidelity_sources/espn.py`). That is a
  separate issue, not this ticket.

## Why: CBS's printed points against its own stat line

Week 8, players with 30+ CBS points. The shared basis: 0.04 per passing yard,
4 per passing TD, −2 per INT, 0.1 per rushing or receiving yard, 6 per
rushing or receiving TD, −2 per fumble lost. It is fractional.

| Pos | n | CBS ÷ shared basis | CBS − shared basis, ppg |
| -- | -- | -- | -- |
| QB | 32 | 1.162 | +2.58 |
| RB | 64 | 0.911 | −0.70 |
| WR | 100 | 0.937 | −0.39 |
| TE | 38 | 0.938 | −0.35 |

- **QB: 6-point passing TDs.** With 6 points per passing TD, the QB ratio is
  0.967.
- **Everyone: a fixed shortfall per yardage category.** The residual is about
  −6.7 for QBs (passing + rushing), −6.9 for RBs (rushing + receiving), −4.2
  for WRs and −3.3 for TEs. It doesn't scale with volume: slope against
  points is about 0. That fits yardage points rounded down each game. The
  shortfall has grown from about 0.3 to about 0.7 ppg for RBs since 10-02.
  The exact CBS formula isn't confirmed.

## Options and their effect on DDF Value (projections)

All three options are measured at the week-8 build, on DDF Value
(projections) at 12 teams. Displayed values are on the 0–70 scale.

| Player | Setting | Now | A: rescore CBS | B: CBS at half weight | C: accept with note |
| -- | -- | -- | -- | -- | -- |
| Jahmyr Gibbs, RB | full PPR | 72.9 | 72.9 | 72.7 | 72.9 |
| Jaxon Smith-Njigba, WR | full PPR | 56.9 | 57.4 | 55.1 | 56.9 |
| Puka Nacua, WR | full PPR | 54.9 | 55.6 | 55.1 | 54.9 |
| Bijan Robinson, RB | full PPR | 53.7 | 53.8 | 53.2 | 53.7 |
| CeeDee Lamb, WR | full PPR | 47.6 | 47.7 | 46.2 | 47.6 |
| Jonathan Taylor, RB | full PPR | 45.2 | 45.2 | 43.2 | 45.2 |
| Bucky Irving, RB | full PPR | 38.8 | 41.5 | 40.1 | 38.8 |
| Zay Flowers, WR | full PPR | 39.5 | 41.4 | 40.5 | 39.5 |
| Chris Olave, WR | full PPR | 27.2 | 27.0 | 25.0 | 27.2 |
| Jalen Coker, WR | full PPR | 22.2 | 21.9 | 25.2 | 22.2 |
| Joe Burrow, QB | full PPR | 16.8 | 15.4 | 15.7 | 16.8 |
| David Montgomery, RB | full PPR | 12.6 | 12.8 | 14.8 | 12.6 |
| Josh Allen, QB | superflex PPR | 49.1 | 48.5 | 50.2 | 49.1 |
| Joe Burrow, QB | superflex PPR | 41.8 | 40.7 | 41.9 | 41.8 |
| Mean move, top 100 | full / half / superflex | — | 0.24 / 0.26 / 0.36 | 0.75 / 0.80 / 0.66 | 0 |

**A. Rescore CBS from its own stat line (recommended).**

- What it does: compute CBS's per-game points from its published stat
  components on the shared basis, instead of using CBS's printed points.
  Values barely move. CBS's per-game numbers shown on the page, and the
  cross-source mean used to fill missing players, stop running 2.5 points
  high on QBs and 1.1 low on RBs.
- Divergence check: the half PPR outliers fall from 45.3% to 41.0%, under the
  45% line. Full PPR falls from 48.9% to 45.3%, just over the line, so the
  warn alone won't clear. Pair A with a resolution note.
- Cost: a change to the CBS pull or leg code, with the Python reference on
  the same branch and a test that fails without it. It is T1, because it
  sets a published number.

**B. Down-weight CBS to half in DDF Value (projections).**

- What it does: it changes the definition of DDF Value (projections) from an
  equal average of the projection sources to a weighted one.
- Effect: it moves the players where CBS's own opinion differs. Jalen Coker
  goes +3.0, David Montgomery +2.2, Chris Olave and Davante Adams −2.2, and
  Jonathan Taylor −2.0.
- The scoring bias stays in CBS's per-game numbers. Dropping CBS entirely is
  the extreme case: mean move 1.9, Coker +7.4, Montgomery +5.5, Kirk Cousins
  −8.1 in superflex.
- I wouldn't do this. The disagreement it removes is CBS's opinion, not an
  error.

**C. Accept as is, with a note.**

- What it does: record the warn in `data/source-divergence-resolutions.json`
  as CBS opinion plus a known scoring basis. Nothing moves.
- Cost: CBS QBs keep showing about 2.5 points a game high wherever CBS's
  per-game numbers appear, and the warn recurs each week until it is noted
  again.

## What I couldn't check

- CBS's published scoring rules weren't read from a CBS page. The 6-point
  passing TDs and the per-category shortfall are fits to CBS's own numbers.
- The A, B and C effects are measured at week 8 only. Weeks 4 to 7 in the
  gap table use the served ppg. The per-player rescore is week 8 only.
- The DDF numbers come from the Python reference (`pipelines/value_reference.py`)
  on the committed week-8 fixture, not from the live page.

## Reproduce

```
python3 docs/research/JEG-1310/cbs_options.py --json /tmp/jeg1310.json
```

`cbsros_2026-10-29_components.txt` is CBS's week-8 stat line, scored on the
shared basis. It was read from `public.cbs_ros_projections.raw_stats` for
`cbs_snapshot_date = '2026-10-29'`, with each component pulled out by key
(`pass_yds`, `pass_td`, `int`, `rush_yds`, `rush_td`, `rec_yds`, `rec_td`,
`fl`). The fit table above came from the same table, for snapshots 10-02,
10-12, 10-19, 10-26 and 10-29.
