## 2026-10-30 - JEG-1239 health watch: exit 3 warns, exit 1 and 2 fail

Contract: carry out Jeremy's pick on JEG-1239's exit-3 policy ("A", 2026-10-30
13:39 UTC: warn only). When the watch cannot verify that this run's artifacts
arrived (exit 3, e.g. a 403 on the served copy), health-artifacts.yml keeps the
run green and flags it as unverified. Stale (1) and not arrived (2) still fail.
The watcher's own exit codes are unchanged.

### Verified (check named)
- `tests/test_health_artifacts_watch_step.py` runs the workflow's watch-step
  script under `bash -e` with a stub watcher. On main's step, exit 3 fails the
  step (`test_unverified_warns_and_stays_green`: 3 != 0). With this change, all
  4 tests pass: 3 gives exit 0 with a `::warning` annotation and the watch log
  still written, and 0, 1 and 2 pass through.
- `python3 -m unittest tests.test_health_artifacts_watch_step
  tests.test_health_artifacts_watch tests.test_health_artifacts_summary_step
  tests.test_health_artifacts_publish`: OK.

### Claimed, not confirmed
- A live run with a real exit 3 has not happened since the change. The next
  scheduled run that hits a 403 should show the warning annotation and a green
  watch step.
