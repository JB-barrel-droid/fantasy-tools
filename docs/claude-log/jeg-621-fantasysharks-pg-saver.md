## 2026-10-30 - JEG-621 Fantasy Sharks saver reads Postgres directly (Mac)

Branch `claude/JEG-621-mac-schedule`. New: `pipelines/lib/pg_direct.py`, `tests/test_pg_direct.py`. Edited:
`pipelines/save_fantasysharks_references.py` (its three hooks now point at `pg_direct`). The razzball saver is unchanged.

The Mac cannot load the REST `sbclient`, so the Fantasy Sharks saver's `fetch_players`, `upsert_rows` and `count_rows` use
`psycopg` with the login from the Keychain (account `fantasy-tools`, service `ddf-supabase-db-url`), read at runtime. The URL is
never printed, logged or written. Upsert is one transaction on the same grain `(player_key, fantasysharks_snapshot_date)`.
Tests use fake connections only. No value math changed.

Dry run on vintage 2026-10-30: 477 clean rows, 2 review rows (position_conflict: Connor Heyward and Max Bredeson). Real save
and the launchd schedule are waiting on Jeremy's answer about Max Bredeson.
