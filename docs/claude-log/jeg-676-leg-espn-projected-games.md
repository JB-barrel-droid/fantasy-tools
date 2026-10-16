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

### Claimed

- Chain will publish week 6 once this merges and the chain dispatches.
