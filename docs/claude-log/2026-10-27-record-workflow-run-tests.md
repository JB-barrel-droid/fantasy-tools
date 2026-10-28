## 2026-10-27 - JEG-1159 record_workflow_run unit tests

Contract: add `tests/test_record_workflow_run.py` covering
`pipelines/lib/record_workflow_run.py` (JEG-137, R10) — the cron fire-time
computation and the idempotent JSON merge — without touching the module.

### Verified (check named)
- `python -m unittest tests.test_record_workflow_run -v` — 9 tests, OK.
  Covers: `compute_cron_at` returns None for empty cron, wrong field count,
  and malformed/non-numeric fields; daily `"30 11 * * *"` at a fixed date
  returns `2026-03-10T11:30:00+00:00` when started_at is after the fire and
  `2026-03-09T11:30:00+00:00` (previous-day rollover) when before it. `main`
  creates a missing nested `--output` file, overwrites the same workflow's
  entry on a second run with no duplicate key, preserves other workflows'
  entries, and records `cron_at`/`cron`/`slip_minutes` null for `--cron ""`.
- Mutation check: deleting the daily rollover in `compute_cron_at`
  (`if intended > started_at: intended = intended - timedelta(days=1)` ->
  `pass`) made `test_daily_before_fire_rolls_back_one_day` fail with
  `'2026-03-10T11:30:00+00:00' != '2026-03-09T11:30:00+00:00'`; reverted with
  `git checkout -- pipelines/lib/record_workflow_run.py`, file clean after.
- No real clock: all datetimes are fixed literals
  (`2026-03-10`/`2026-03-09`).
- `python -m unittest tests.test_record_workflow_run` re-run after merging
  `origin/main` — OK (see commit).

### Claimed, not confirmed
- That these are the only behaviours the chain reader depends on from this
  module; only the ticket's named criteria are covered.
- Done by an OpenRouter `deepseek/deepseek-v4.1-flash` run; untrusted until a
  Claude review.
