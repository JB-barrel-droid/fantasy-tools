# 2026-10-28 Source lateness: what late means per source, alerted hourly (JEG-1200, part of JEG-1201)

Session: Claude Duet "Keep every source fresh through the week change" lane.
Branch `be/jeg-1200-source-late`.

## Why

Jeremy (Oct 28): "dynamic sources should update daily, and never late for a
week"; "Projection sources update constantly, so they should never be
delayed. So does fantasycalc. Trade chart articles tend to publish at the same
time every week."

Found while reading the probe state and log (Supabase, read only, 13:45Z):
- Every source already re-ingests at least daily when its ingest works
  (`source_probe` max_age 20 h; FantasyCalc 24 h). What was missing was
  noticing when that stops.
- FantasySharks: every probe 403 since at least Oct 22, never saved, 9
  attempts. No alert.
- The probe log has no rows at all for Oct 20 and 21. No alert.
- Board: the site still serves week 7 for every source (history index
  fixture_built_at 2026-10-26 15:42Z) while all trade charts published week 8
  on Oct 27.

## What changed

- `pipelines/source_lateness.py`: a rule per source (live, weekly article,
  reference), three lightweight checks (change check silent, not confirmed
  current, week late), report JSON, one `source-late` GitHub issue.
- `.github/workflows/source-lateness.yml`: hourly at :50, its own schedule on
  purpose (it watches the pg_cron schedules); listed as unmonitored in
  `config/monitoring_coverage.json` with the reason.
- `docs/source-lateness.md`: the rules and what to do.
- `tests/test_source_lateness.py` (wired into `make test-unit`).

## Verified (check named)

- `python3 -m unittest tests.test_source_lateness tests.test_monitoring_coverage
  tests.test_gha_schedules_pg_cron` OK.
- Replayed against the live probe state at 2026-10-28 13:55Z: 5 late
  (FantasyCalc, ESPN, CBS ROS, Razzball: site on week 7; FantasySharks: never
  saved, 403). At Wed 12:01 CT the three trade charts join ("week 8 chart is
  out but the site still shows week 7").

## Claimed, not confirmed

- The workflow's first scheduled run on main and the issue it opens (checked
  after merge).
