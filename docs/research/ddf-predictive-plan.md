# DDF Value: predictive aggregation -- internal plan

JEG-943. Branch `research/ddf-predictive-aggregation`. 2026-10-23.

## 1. Data inventory

### What exists

| Data | Location | Coverage | Schema |
|---|---|---|---|
| ROS projections per source per week | `data/history/week-N.json` (N=2..7) | 2026 wk 2-7; all 7 sources from wk 4 | `sources.<key>.ppg.<player_key>` = `[std, half_ppr, ppr]` for projections; `sources.<key>.natives.<scoring>.<player_key>` = value for charts |
| ESPN week-ahead projections | `data/inputs/espn_weekly_projections_2026.csv` | 2026 wk 1-7, ~500 players/wk | `season, week, player_key, pos, team, std, half_ppr, ppr, snapshot_at, pre_kickoff, basis` |
| RotoWire week-ahead (via Sleeper) | `data/inputs/weekly_projections_sleeper.csv.gz` | 2018-2026, ~350-400 players/wk | `season, week, sleeper_id, gsis_id, name, pos, team, opponent, company, updated_at, pts_std, pts_half_ppr, pts_ppr` |
| Actuals (2024-2026) | `data/inputs/weekly_actuals_2024_2026.csv` | 2024-2026 (2026 through wk 6, wk 7 partial) | `season, week, player_key, pos, team, std, half_ppr, ppr` |
| Actuals (nflverse 2015-2025) | `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz` | 2015-2025 full seasons | `season, week, player_id, name, pos, team, std, half_ppr, ppr` |
| Player identity | `data/fixtures/current/players.json`, `data/inputs/player_identity_map.json` | Current universe (1,163 players) | `player_key`, Sleeper ID mapping partial |
| Injury/status history | Supabase `player_status_history` | Daily snapshots since ~wk 5 | `snapshot_date, sleeper_id, player_key, status, injury_status, ...` |

### Critical gaps

1. **No CBS ROS or Razzball week-ahead projections stored.** These sources publish week-ahead numbers but the repo captures only rest-of-season. This is the single biggest gap blocking the full evaluation.
2. **No complete 2026 actuals past week 6.** Week 7 has 18 rows (likely only Thursday games). Actuals update weekly.
3. **Sleeper/RotoWire identity mapping to player_key is incomplete.** The `gsis_id` field maps to nflverse but not directly to `player_key`. A join through `player_identity_map.json` or the players table is needed. Coverage of this mapping is unknown.
4. **No prior-season projection history from ESPN/CBS ROS/Razzball in the same format.** The 2018-2026 RotoWire data via Sleeper is the only multi-season weekly projection source. It is one company's projections, not the three DDF Value uses.
5. **No ROS-to-end-of-season ground truth.** Evaluating rest-of-season accuracy requires the season to end. 2026 is incomplete; 2024-2025 have actuals but no saved ROS projections from ESPN/CBS ROS/Razzball.

### Proposed storage (JEG-944)

A pipeline that, each week before Sunday kickoff, saves each projection source's week-ahead per-game projection:

```
weekly_projection_snapshots(
    season      int,
    week        int,
    source      text,      -- 'espn', 'cbsros', 'razzball'
    player_key  bigint,
    scoring     text,      -- 'standard', 'half_ppr', 'ppr'
    ppg         float,
    type        text,      -- 'week_ahead' or 'ros'
    snapshot_at timestamptz
)
```

ESPN is already saved in this form (the CSV). CBS ROS and Razzball week-ahead projections need a new puller or scraper. The ROS values from `data/history/week-N.json` should also be written into this table for uniformity.

## 2. Evaluation protocol

See research post 10, section "Evaluation protocol for the full study". Summary:

- **Targets:** (a) week-ahead PPR points per game; (b) rest-of-season points above waivers (scored at season end). Stratified by early/mid/late season per Jeremy's note on declining bench value.
- **Splitting:** rolling-origin, time-ordered, no leakage.
- **Metrics:** MAE, RMSE, rank correlation, calibration by position and tier, value-above-waivers error.
- **Baselines:** equal-weight mean (current), median, best single source.
- **Uncertainty:** bootstrap CIs clustered by player; no claims from tiny samples.

## 3. Ticket breakdown (ordered)

| # | Ticket | Blocked by | Effort | Status |
|---|---|---|---|---|
| 1 | JEG-944: Store weekly projection snapshots | -- | Medium | Todo |
| 2 | Align Sleeper/RotoWire identity to player_key | JEG-944 | Small | Not filed |
| 3 | JEG-945: Backtest source accuracy vs actuals | JEG-944 + 8 weeks of data | Large | Todo, blocked |
| 4 | JEG-946: Research post 10 (full version) | JEG-945 | Medium | In Progress (draft done) |
| 5 | Implement weighted aggregation if data supports it | JEG-945 decision | Medium | Not filed |
| 6 | End-of-season retrospective: ROS accuracy | Season end | Medium | Not filed |

## 4. Preliminary backtest results (2026-10-23)

Using ROS projections vs single-game actuals (a noisy proxy):

| Source | N | MAE | 95% CI |
|---|---|---|---|
| ESPN (ROS) | 1,425 | 4.68 | [4.46, 4.91] |
| CBS ROS | 703 | 5.05 | [4.74, 5.36] |
| Razzball (ROS) | 1,171 | 4.50 | [4.22, 4.75] |
| ESPN (weekly) | 1,600 | 4.36 | [4.17, 4.56] |
| Equal mean | 1,122 | 4.61 | [4.37, 4.87] |
| Inverse-error weighted | 1,122 | 4.61 | [4.37, 4.87] |

**Finding:** equal weights and inverse-error weights produce the same MAE to three decimal places. The differences between sources are within the 95% CIs. Five weeks of data cannot distinguish the sources.

**Verified:** script output matches the JSON/MD written by `source_accuracy_backtest.py` (all numbers from one script run, no manual numbers). ROS-vs-actuals is the wrong test for week-ahead accuracy (stated as a limit).

**Claimed but not verified:** that the CI overlap means the true ranking could change with more data. (This is a statistical truism, not a testable claim on current data.)

## 5. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| CBS ROS / Razzball do not publish week-ahead projections in a scrapeable form | Cannot compare all three sources on the right target | Use ROS as proxy; add RotoWire as an independent weekly source |
| Season too short for stable weights | Any fitted weights overfit one season | Default to equal weights; require two seasons for production changes |
| Source accuracy changes year to year | Weights from 2026 may be wrong for 2027 | Rolling evaluation; decay older data |
| Missing actuals data gaps (bye weeks, late-season additions) | Biased evaluation | Exclude bye-week zeros or model them explicitly |
| Identity mapping gaps (Sleeper to player_key) | Lose RotoWire data for some players | Invest in identity resolution pipeline |

## 6. Decay definition (first-class deliverable)

Jeremy (2026-10-23): "You need to resolve what decay should be before making changes to the dashboard."

### What the expected-starts model already handles
- Bye share declining to 0 from week 15 (ES-1)
- Sigma drift scaling with sqrt(remaining weeks) (ES-1)
- Lineup share computed fresh each week from that week's parameters

### What it does NOT handle
- Option/breakout value declining as the season progresses (manifesto sec 5, ES-8 excluded)
- Discounting of later weeks (manifesto sec 9, excluded)
- Whether source weights should change by season phase

### Relation to post 1 revision (PR #846)
Post 1 lists "mid-season improvement not modeled" as a limitation and prerequisite for publication. That is the upward component; the decay is the downward component. The two do not conflict and should be resolved together.

### Decision needed
See the handback for the multiple-choice question on decay.

## 7. Decisions for Jeremy

These are in the handback as multiple choice. Nothing here changes production values.
