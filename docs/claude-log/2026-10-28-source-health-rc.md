## 2026-10-28 - Source-health release candidate (JEG-1180 / JEG-1200)

Contract: combine the already reviewed fixes from draft PRs #1022 and #1042
on current main, verify their behavior together, and open a draft candidate.
Parent owns the release and production verification.

### Verified (check named)

- GitHub PR reads: #1022 `0ebd8d0f` and #1042 `9ebbd360` were open drafts;
  current main was `3919f998` before combination.
- Local `git merge` of #1022 then #1042 into current main: no conflicts;
  `git diff --check` passed. No source isolation or workflow guard file edited.
- `python3 -m unittest tests.test_week_stale tests.test_reference_freshness
  tests.test_sync_health_freshest tests.test_week_state
  tests.test_check_weekly_freshness tests.test_watchdog_common_helpers
  tests.test_source_lateness tests.test_source_probe
  tests.test_monitoring_coverage tests.test_gha_schedules_pg_cron
  tests.test_timestamps`: 207 passed.
- `python3 -m unittest tests.test_source_health_release
  tests.test_week_stale tests.test_source_lateness tests.test_validate_shards`:
  72 passed. The new combined regression checks served-week truth, the
  Wednesday lateness deadline, Thursday staleness, and warning-only freshness.

### Claimed, not confirmed

- Combined draft PR's preview, render and aggregate CI remain pending.
- Parent's latest-main integration, merge order and live verification.
