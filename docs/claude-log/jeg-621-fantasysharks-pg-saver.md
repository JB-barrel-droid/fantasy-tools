## 2026-10-30 - JEG-621 Fantasy Sharks saver reads Postgres directly (Mac)

Branch `claude/JEG-621-mac-schedule`. New: `pipelines/lib/pg_direct.py`, `tests/test_pg_direct.py`. Edited:
`pipelines/save_fantasysharks_references.py` (its three hooks now point at `pg_direct`). The razzball saver is unchanged.

The Mac cannot load the REST `sbclient`, so the Fantasy Sharks saver's `fetch_players`, `upsert_rows` and `count_rows` use
`psycopg` with the login from the Keychain (account `fantasy-tools`, service `ddf-supabase-db-url`), read at runtime. The URL is
never printed, logged or written. Upsert is one transaction on the same grain `(player_key, fantasysharks_snapshot_date)`.
Tests use fake connections only. No value math changed.

Dry run on vintage 2026-10-30: 477 clean rows, 2 review rows (position_conflict: Connor Heyward and Max Bredeson). Real save
and the launchd schedule are waiting on Jeremy's answer about Max Bredeson.

### Real save and schedule (Jeremy's pick, Oct 30 4:12 PM CT)
Saved 477 rows for vintage 2026-10-30 with Connor Heyward and Max Bredeson left out (both position_conflict; the Bredeson
mapping is untouched and gets fixed later if the check finds an error). The save's own check read back 477 rows; a direct query
found 477 rows and 477 distinct player_keys, and neither excluded name present. The identity-queue writer printed a warning
(no SUPABASE_URL on the Mac); the save was unaffected.

`ops/mac/run_fantasysharks_daily.sh` pulls with `--delay 60` then saves; `ops/mac/com.ddf.fantasysharks-daily.plist.template`
runs it at 6:15 AM local (the Mac is on Central time) as launchd label `com.ddf.fantasysharks-daily`, log
`~/Library/Logs/fantasysharks-daily.log`. Installed for now from this worktree path: after merge, re-render the template against the
main checkout and reload.
