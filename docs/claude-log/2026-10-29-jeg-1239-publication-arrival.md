## 2026-10-29 - JEG-1239 health-artifact publication arrival

Contract: make "this run's published health artifacts reached the served site"
an explicit, machine-readable outcome in `pipelines/health_artifacts_watch.py`,
so a valid but older served copy no longer counts as arrival. Content
freshness (720-minute limit), publication arrival and source coverage stay
separate. Offline only: no workflow, Supabase, deploy or #1081/#1083 change.

### Verified (check named)
- Failing before: `PublicationArrivalTest.test_valid_old_served_copies_past_the_wait_are_not_arrival`
  run against main's watcher (`git show HEAD:pipelines/health_artifacts_watch.py`)
  fails with `AssertionError: 0 == 0 : valid but older served copies must not
  count as this run's arrival`, after the full 25-minute window on a fake clock
  and with both served copies (fixtures, 386 / 109 minutes old) judged fresh.
  Passes after the change with exit 2.
- `python3 -m unittest tests.test_health_artifacts_watch`: 25 tests OK (the 9
  existing ones unchanged and passing, 16 new): arrival, boundary (equal
  timestamp arrives, 1 microsecond older does not), arrival on the last poll
  inside the window, late arrival seen by the judging fetch, partial arrival of
  the pair, missing and malformed served timestamps, a published copy without
  a timestamp, HTTP 403 throughout, fetch error, 403 then recovery, old copy
  then a denied judging fetch, fetch_json keeping the 403 status, no-await
  compatibility, and the legacy `await_published` return value.
- Mutation 1, arrival comparison removed (`elif served >= expected:` ->
  `elif True:`): 9 failures, including the reproduction, the existing
  `test_waits_for_this_runs_deploy_before_judging`, the boundary and partial
  arrival tests. Mutation 2, arrival dropped from the exit policy: 3 failures,
  the reproduction (`0 == 0`), mismatch and partial-arrival tests (`2 != 0`).
  Both restored afterwards.
- Neighbouring focused tests OK: `tests.test_health_artifacts_summary_step`,
  `tests.test_monitoring_coverage` (check-id `contains` rows still match),
  `tests.test_gha_schedules_pg_cron`, `tests.test_producers_schedule_tidy`.

### Claimed, not confirmed
- Caller impact: the only caller is the "Watch served artifacts" step of
  `.github/workflows/health-artifacts.yml` (unchanged). It runs `set -o
  pipefail` with `tee`, so exit 2 or 3 marks that step and the run red; every
  later step is `if: always()`, so the summary, alerts and ops status still
  run. Read from the workflow file, not from a live run.
- Supabase observations are unchanged apart from `p_http_status`, which now
  carries the HTTP code of a denied fetch (e.g. 403) instead of null.
- No browser check was possible in this sandbox; none is needed for this
  Python-only change. Live served artifacts were not fetched.
