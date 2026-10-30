# JEG-1195: the unapplied JEG-1268 migration moves out of supabase/migrations

Session: cloud thread "Overnight board burn-down", on the coordinator's ask (#1083 owner idle since 17:11 UTC Oct 29).

## What changed
- `supabase/migrations/jeg1268_weekly_fantasypros_shown_check_20261029.sql` moved, content unchanged, to
  `docs/research/proposed-migrations/`. Its own header says PROPOSED, NOT APPLIED; merging it under
  `supabase/migrations/` would put an unapproved migration where migration tooling picks files up.
- `tests/test_weekly_fantasypros_contract.py` reads applied migrations, then that proposed folder, through one
  `migration_files()` helper. No assertion changed: the follow-up checks still require the proposal to replace the
  constraint in one statement and to be marked PROPOSED.
- `docs/research/jeg-1195-weekly-inputs-readiness.md`: the one path reference follows the file.

## Verified (check named)
- `python3 -m unittest tests.test_weekly_fantasypros_contract`: with the file moved and the test unchanged, 10+
  failures ("no migration defines weekly_fantasypros_pages_shown" and the half-null cases); with the helper, OK
  (skipped=1, the real-Postgres case).
- `python3 -m unittest tests.test_monitoring_coverage tests.test_gha_schedules_pg_cron`: OK.

## Claimed, not confirmed
- Nothing was applied to Supabase. Applying JEG-1268 still needs Jeremy's yes naming it.
