## 2026-10-16 - JEG-676/JEG-535: align ESPN leg denominator to espn_projected_games

**Ticket:** JEG-676 (week 6 publish deadlock), JEG-535 (per-game-played math)

### Root cause

PR 559 (JEG-535) changed `bake_players.py` to divide ESPN ROS by
`espn_projected_games` (non-zero ROS weeks per player) instead of team games.
`build_ddf_two_tier_leg.py` still divided by team games (`games_in_window`).
When the chain re-runs the puller (which now emits `espn_projected_games` in
the CSV), the two paths diverge for any player whose projected games differ
from team games (e.g. PHI: 11 projected vs 12 team), failing
`test_players_json_matches_leg_per_game` for 42 players.

### Change

`pipelines/build_ddf_two_tier_leg.py` `load_espn_lists`: read
`espn_projected_games` from the CSV row, use it as the denominator when
present, fall back to team games when absent (backward compat with old CSVs).
Updated metadata strings to document the new divisor.

### Verified

- `test_players_json_matches_leg_per_game` passes (with current CSV that lacks
  the column, so fallback path exercised; the chain will exercise the primary
  path when the puller runs).
- Full test suite passes (excluding pre-existing `test_score_lineup_values.py`
  import error from `es.ROSTER`).

### Second fix

`tests/test_static_export.py` `espn_anchor_problems`: same team-games
denominator mismatch. Applied same pattern. Commit 1fee301c.

### Chain results

- Run 38841934175: `test_espn_anchor_matches_committed_inputs` failed (126
  players). Fixed by second commit.
- Run 38842224006: ESPN anchor and leg parity tests pass. Chain blocked on
  `test_week_history.DeltaRecomputeTest`: CBS served week != chart (CBS
  review-held at week 5, chain built week 6). Razzball and ESPN also
  review-held. These are the expected JEG-667 coverage holds, not caused by
  this fix.

### Remaining blockers for week 6

- CBS/razzball/espn review holds need human review (JEG-667 scope)
- `test_week_history` served-week delta mismatch (consequence of review holds)
