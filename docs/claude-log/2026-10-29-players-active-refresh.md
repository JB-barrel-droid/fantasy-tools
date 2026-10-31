## 2026-10-29 - JEG-1354 players.active refresh

Contract: find why `public.players.active` is false for current starters and
build the fix as code only, with no production write (Jeremy's yes comes later).

### Verified (check named)
- Cause: the archived nflverse loader
  (`archive/2026-10-07/weekly_vegas/pipeline/loaders/nflverse.py`) inserted
  players with `active = status == "ACT"` from the first roster season it saw
  and never upserted. Every original row (player_key below 4647, gsis id, no
  sleeper_id) carries that flag; no current pipeline, function, trigger or
  cron job writes it (repo search; `pg_proc` search for writes to players).
- Size: read-only SQL on 2026-10-29 against `player_status_history` (today's
  Sleeper rows, already resolved through PlayerIndex) found 281 skill rows
  with `active=false` that are on an NFL team with news this year, each
  claimed by one Sleeper id, including all 12 starters named on the ticket.
  The other ~576 false rows are not on a team today.
- `tests/test_sync_players_active.py`: 12 tests pass. Removing the id-only
  rule for turning a row off makes
  `test_retired_player_reached_by_name_only_keeps_its_flag` fail. The module
  does not exist on origin/main, so the test file fails there.
- `tests.test_run_suite` and `tests.test_validate_shards` pass with the new
  Makefile line; the workflow YAML parses.

### Claimed, not confirmed
- The exact counts the script will print in CI (it reads the committed
  Sleeper base, not today's live pull). The deactivation count was not sized.
- Nothing was written to Supabase. The workflow step stays a dry run until the
  repository variable `PLAYERS_ACTIVE_SYNC` is set to `write`.
