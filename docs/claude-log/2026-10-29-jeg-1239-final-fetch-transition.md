## 2026-10-29 - JEG-1239 correction: arrival reflects the judged copy

Contract: Codex review f97f58ed on #1106 `5d7a32e`. Once a poll saw this
run's copy, the arrival outcome froze at `arrived`, so (a) a previous copy at
the judging fetch still exited 0 as arrived and (b) a 403 at the judging fetch
kept `arrived` with the earlier HTTP 200. This corrects the earlier entry
`2026-10-29-jeg-1239-publication-arrival.md`, whose "late arrival / denied
judging fetch" wording only held when the wait had not seen arrival.

### Verified (check named)
- `tests.test_health_artifacts_watch`: 27 OK (25 before plus
  `test_arrival_seen_then_previous_copy_at_judgment_is_not_arrived` and
  `test_arrival_seen_then_denied_judging_fetch_is_unverified`). Both new tests
  fail against `5d7a32e`'s watcher with `('arrived', None)` and
  `('arrived', None, 200)`.
- Mutation restoring the old gate (re-judge only when the wait had not seen
  arrival): exactly the two new tests fail. Earlier mutations re-run: arrival
  comparison removed, 10 failures; exit policy ignoring arrival, 4 failures.
- Also OK: `tests.test_health_artifacts_summary_step`,
  `tests.test_monitoring_coverage`, `tests.test_gha_schedules_pg_cron`,
  `tests.test_producers_schedule_tidy`.

### Claimed, not confirmed
- Contract now: each artifact's `outcome`, `reason`, `served_at` and
  `http_status` describe the copy judged after the wait (the same fetch the
  freshness check reads); the wait's last observation is kept under
  `observed_during_wait`. The exit code reads only the current outcome.
- Exit 3 (unverified) fail-closed versus warning-only is still the open
  policy question; no Supabase check added.
