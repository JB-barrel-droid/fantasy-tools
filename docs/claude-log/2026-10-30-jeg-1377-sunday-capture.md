# JEG-1377: Sunday pre-kickoff capture, DST check, retry, alert, dry run

Session: cloud thread "Overnight board burn-down", Jeremy's overnight sweep, 2026-10-30.
Branch `claude/JEG-1377`. No value math, no Supabase write, no migration, no deploy.

## Changed
- `projection-capture-sunday.yml`: the pull and capture step tries three times, 2 then 4 minutes apart.
- `espn-weekly-store.yml`: a Sunday backstop step (Sunday from 16:00 UTC only) re-runs the CBS and Razzball pull plus `capture_projections_only.py` when a capture is missing; the capture check now runs with `--pre-kickoff`.
- `pipelines/lib/projection_capture.py`: `required_cells(..., sunday_due=)`, with `SUNDAY_DUE` (Monday 12:00 UTC, unchanged default) and `SUNDAY_DUE_PRE_KICKOFF` (Sunday 16:00 UTC).
- `pipelines/check_projection_captures.py`: `--pre-kickoff` flag.
- `pipelines/capture_projections_only.py`: the dry run builds both sources' capture rows, writes nothing, and exits 1 under a row floor (before, it only parsed Razzball and returned 0).
- `tests/test_projection_capture_sunday_jeg1377.py` (in `make test-unit`), docs `docs/projection-captures.md`.

## Verified (check named)
- Live read-only SQL: pg_cron `projection-capture-sunday` (jobid 48, `30 15 * * 0`) active with no run history; `cron.timezone` = GMT; `espn-weekly-store-sunday` (jobid 39) dispatched and ran 2026-10-25 16:20 UTC.
- `python3 -m unittest tests.test_projection_capture_sunday_jeg1377 tests.test_projection_captures`: 47 OK. With the source and workflow changes stashed, 8 of the 11 new tests fail (the 3 DST tests pin behavior that was already right).

- `python3 -m unittest tests.test_monitoring_coverage`: OK after adding `jeg1140-settings-render.yml` to the no-schedule list (it was red on main, from #1129).

## Claimed, not confirmed
- The dry run on the branch through workflow_dispatch (see the PR for the run link once it finishes).
