## 2026-10-23 - JEG-544 research post 1 revision

Contract: revise research post 1 (bench player value) from internal draft to
public-facing article, addressing all of Jeremy's Google Doc review comments.

### Verified (check named)

- Missed-game rate variance computed from `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`:
  QB mean 7.9% (sd 1.0pp), RB 12.5% (sd 2.5pp), WR 11.0% (sd 1.3pp), TE 11.2% (sd 1.5pp).
  Recent 5-year rates within ~0.7pp of 11-year average.
- `PIE_PER_STARTING_SLOT = 28.0` confirmed at `pipelines/expected_starts_model.py:80`;
  methodology doc OC-1 confirms it as a design choice (28 per starting slot).
- Backup definition matches engine: `depth_round_starts.py:10` ("depth round 1 = first backup"),
  computed as players ranked past starters (top S) at each position.
- Starter downside IS modeled: `position_components` line 249 applies `prob_band(x, s, l, inf)`
  to all players including starters. JEG-550 (Done) confirmed this. But the magnitude is
  not broken out in the readout.
- Config missed-game rates (`config/lineup_parameters.json`): QB 0.118, RB 0.144, WR 0.107,
  TE 0.151 (recent 5-year). These are the model defaults.

### Claimed, not confirmed

- Bench-share readout numbers (10.0% overall, per-position splits, sensitivity table)
  are carried forward from the prior draft; not re-run in this session because the
  engine has not changed since the convention-tier run of 2026-10-16.
- Fill-in rates table (0.28/0.30/0.33/0.21 for first backup) carried forward from
  JEG-551 verification; not re-run.
