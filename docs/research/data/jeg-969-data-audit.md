# JEG-969 Lane B Step 1: Data Audit

Written 2026-10-23. All counts verified against the files and Supabase
(project iskiybsimubiujwuchsl, READ-ONLY).

## Data inventory

### 1. ROS projections per source per week (file)

Location: `data/history/week-N.json` (N = 2..6 on main; week-7.json not yet
written as of today).

| Week | ESPN | CBS ROS | Razzball |
|------|------|---------|----------|
| 2    | yes  | no      | no       |
| 3    | yes  | no      | yes      |
| 4    | yes  | yes     | yes      |
| 5    | yes  | yes     | yes      |
| 6    | yes  | yes     | yes      |

Format: `sources.<key>.ppg.<player_key>` = `[std, half_ppr, ppr]`.

### 2. ROS projections in Supabase (source_projection_captures)

22,437 rows, all from a `backfill` capture phase (no live midweek or Sunday
captures yet). Schema: source, season, source_week, capture_at, capture_phase,
horizon, target_week, player_key, scoring_format, points, ppg, games, basis,
batch_id.

| Source   | Weeks   | Distinct players per week | Scoring formats |
|----------|---------|--------------------------|-----------------|
| espn     | 2-7     | 350-588                  | standard, half_ppr, full_ppr |
| cbs      | 4-7     | 349-367                  | standard, half_ppr, full_ppr |
| razzball | 3-7     | 511-641                  | standard, half_ppr, full_ppr |

All rows have horizon = `ros`, ppg only (no week-ahead). These are the same
ROS projections as in the history JSON files, denormalized into the DB.

### 3. ESPN week-ahead projections (file)

Location: `data/inputs/espn_weekly_projections_2026.csv`.
Coverage: 2026 weeks 1-7, ~500 players/week. Columns: season, week,
player_key, pos, team, std, half_ppr, ppr, snapshot_at, pre_kickoff, basis.
Keyed by player_key (matches the repo universe).

### 4. RotoWire week-ahead via Sleeper (file)

Location: `data/inputs/weekly_projections_sleeper.csv.gz`.
Coverage: 2018-2026, ~350-400 players/week, 17-18 weeks/season, 52,462 rows
total. Columns: season, week, sleeper_id, gsis_id, name, pos, team, opponent,
company, updated_at, pts_std, pts_half_ppr, pts_ppr.

Identity mapping: `data/inputs/sleeper_projection_idmap.csv` (on branch
`origin/data/fourth-projection-source`, PR #850). Match rate: 82% of rows
(42,231 of 51,641 QB/RB/WR/TE rows) have a player_key. Unmatched are mostly
retired players (Tom Brady, Julio Jones, etc.) not in the current players
table. For active 2025-2026 projected players, the match rate is effectively
100% (report: `gsis_known_but_not_in_players_projected_2025_or_2026 = 0`).

### 5. Actuals

| File | Coverage | Rows | Key |
|------|----------|------|-----|
| weekly_actuals_2024_2026.csv | 2024 wk1-18, 2025 wk1-18, 2026 wk1-6 | 14,071 | player_key |
| weekly_actuals_nflverse_2015_2025.csv.gz | 2015-2025 full seasons | 61,977 | player_id (gsis_id) |

2026 week 7 actuals: **not yet in file** (0 rows for week 7). Week 6: 246
players.

### 6. Player identity

- `data/fixtures/current/players.json`: current universe (~1,163 players with
  player_key).
- `data/inputs/player_identity_map.json`: name-based map (530 canonical, 593
  aliases). Not useful for sleeper_id lookups.
- Sleeper ID map (PR #850): sleeper_id -> gsis_id -> player_key. 902 matched
  of 1,275 total sleeper_id entries.

## Which tests are valid NOW

### A. Per-source ROS accuracy against single-week actuals (2026)

**Valid.** ESPN, CBS ROS, Razzball ROS ppg vs actual PPR points, weeks 2-6
(using file data). This is what `source_accuracy_backtest.py` already runs.
Limitation: ROS ppg is not a week-ahead projection. Five data-weeks, ~700-1,425
player-weeks per source. CIs overlap; cannot rank sources.

### B. ESPN week-ahead accuracy (2026)

**Valid.** ESPN weekly projections weeks 1-6 vs actuals. ~500 player-weeks per
week. Already done in the backtest; ESPN weekly (MAE 4.36) beats all ROS
sources, as expected.

### C. RotoWire week-ahead accuracy (2018-2025, single-source)

**Valid with identity join.** Join sleeper_projection_idmap (from PR #850
branch) on sleeper_id to get gsis_id, then join nflverse actuals on
player_id = gsis_id. Coverage: 2018-2025, 42k+ matched rows (QB/RB/WR/TE).
This is a single-source calibration/shrinkage test across 8 seasons.

Tests possible:
- C1. Per-season RotoWire MAE/RMSE/bias
- C2. Position-specific accuracy
- C3. Calibration (does the projection spread predict the outcome spread?)
- C4. Shrinkage: does regressing toward position mean improve accuracy?

### D. Aggregator comparison: equal vs inverse-error vs median (2026 ROS)

**Valid but underpowered.** Already run by the backtest script. Five weeks of
ROS data cannot distinguish aggregators. The result (equal = inverse-error to
3 decimal places) is the correct preliminary finding.

### E. RotoWire vs ESPN week-ahead (2026 overlap)

**Valid for weeks 1-6.** Both have 2026 week-ahead projections, joined via
sleeper_id -> player_key. Can compare two sources head-to-head on the correct
target (week-ahead vs actual). About 300-400 overlap players per week.

### F. Cross-season source stability (RotoWire only, 2018-2025)

**Valid.** With 8 seasons of RotoWire data, can test whether RotoWire accuracy
varies year to year, by position, by tier. This is single-source only (no
other source has multi-season week-ahead data).

## Tests that WAIT for stored week-ahead data

### G. Three-source week-ahead comparison (ESPN + CBS ROS + Razzball)

**Blocked.** CBS ROS and Razzball do not have stored week-ahead projections.
The Supabase captures are all ROS/backfill. The JEG-944 pipeline (PR #849)
must begin capturing midweek + Sunday week-ahead projections from all three.

**When decidable:** After 8 weeks of stored week-ahead captures from all three
sources (post 10's protocol minimum). If captures start at week 8, this becomes
testable at **week 16 of the 2026 season** (approximately late December 2026 /
early January 2027). With a full 2027 season added, the comparison is robust.

### H. Inverse-error or stacking weights on the correct target

**Blocked by G.** Needs three-source week-ahead data.

### I. Horizon-dependent (early/mid/late) weight changes

**Blocked by G + a full season.** Needs 17+ weeks across early/mid/late strata.
Not decidable before end of 2027 season at earliest.

### J. Rest-of-season accuracy (season-end ground truth)

**Blocked until 2026 season ends** (week 18, ~January 2027). Even then, only
one season of ROS projections is stored.

## Summary table

| Test | Valid now? | Data needed | Decidable when |
|------|-----------|-------------|----------------|
| A. Per-source ROS vs actuals | Yes (5 weeks) | Files on main | Now |
| B. ESPN week-ahead accuracy | Yes (6 weeks) | Files on main | Now |
| C. RotoWire multi-season accuracy | Yes (8 seasons) | Files + PR #850 idmap | Now |
| D. Aggregator comparison (ROS) | Yes but underpowered | Files on main | Now |
| E. RotoWire vs ESPN week-ahead | Yes (6 weeks) | Files + PR #850 idmap | Now |
| F. Cross-season RotoWire stability | Yes | Files + PR #850 idmap + nflverse | Now |
| G. Three-source week-ahead | No | JEG-944 captures | Week 16 2026 (~Dec) |
| H. Weighted aggregation on correct target | No | G | Week 16+ 2026 |
| I. Horizon-dependent weights | No | G + full season | End of 2027 |
| J. ROS accuracy (season end) | No | 2026 season completion | Jan 2027 |
