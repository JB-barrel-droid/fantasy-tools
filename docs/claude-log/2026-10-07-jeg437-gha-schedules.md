# JEG-437 GAP-GHA-SCHEDULES: GHA schedules → pg_cron

Session date: 2026-10-07
Branch: jeg437-gha-schedules
PR: open (see PR title for number after push)

## Work done

Merged origin/main into jeg437-gha-schedules (one conflict in docs/claude-log.md;
resolved by keeping both entries). Validated that the WIP state already had:

- `supabase/migrations/gha_schedules_pg_cron.sql`: three `cron.schedule()` calls for
  pages-deploy-live `30 11 * * *`, weekly-dashboard-load-live `7 16 * * *`,
  sleeper-identity-refresh-live `17 9 * * 2,4`.
- Live Supabase: jobids 27/28/29 active, confirmed via
  `select jobid, jobname, schedule, active from cron.job`.
- `.github/workflows/pages.yml`, `weekly-dashboard-load.yml`,
  `sleeper-identity-refresh.yml`: no uncommented `schedule:` block;
  each has `workflow_dispatch:` (pg_cron dispatches via `dispatch_gha_workflow`).
- `config/monitoring_coverage.json`: all three workflows have `scheduler: pg_cron`
  and `pg_cron_job` naming the live jobs.
- `tests/test_gha_schedules_pg_cron.py`: five tests, all passing, including four
  negative tests (see below).
- `make validate` exit 0 (Python 3.12, CHROMIUM_PATH set).

## Negative-test results (Guard ID: test_gha_schedules_pg_cron)

Each negative test was verified both FAILING on a simulated broken state and PASSING
against the real repo. All five tests pass:

| Test | Broken state simulated | Result on broken state |
|------|----------------------|----------------------|
| test_a_github_schedule_is_caught | Re-adds `schedule:` block to each of the three workflows in turn | problems() contains `"GitHub schedule"` for that workflow |
| test_missing_workflow_dispatch_is_caught | Removes `workflow_dispatch:` from pages.yml | problems() contains `"no workflow_dispatch"` |
| test_missing_or_wrong_cron_job_is_caught | Replaces job name with `'other-job'`; replaces cron with `'0 0 * * *'` | problems() names the original job/cron |
| test_manifest_naming_another_scheduler_is_caught | Sets pages.yml to `scheduler: github_schedule` in manifest | problems() contains `"manifest does not name"` |
| test_real_repo_is_clean | (positive test) | no problems() |

Output from `python3 -m unittest tests.test_gha_schedules_pg_cron -v`:
```
test_a_github_schedule_is_caught ... ok
test_manifest_naming_another_scheduler_is_caught ... ok
test_missing_or_wrong_cron_job_is_caught ... ok
test_missing_workflow_dispatch_is_caught ... ok
test_real_repo_is_clean ... ok
Ran 5 tests in 0.003s OK
```

## Verified

- `select jobid, jobname, schedule, active from cron.job order by jobid` returned
  rows 27–29 (pages-deploy-live, weekly-dashboard-load-live, sleeper-identity-refresh-live)
  all active with correct schedules (matches the migration SQL exactly).
- No uncommented `schedule:` blocks in any .github/workflows/*.yml file
  (`grep -P "^  schedule:" .github/workflows/*.yml` returns empty).
- All three workflows have `workflow_dispatch:` trigger.
- `tests/test_gha_schedules_pg_cron.py` 5/5 pass.
- `tests/test_monitoring_coverage.py` 25/25 pass.
- `make validate` exit 0 (Python 3.12).

## Claimed, not confirmed

- Both GitHub scheduler and pg_cron fire until this PR merges; all three workflows
  are idempotent (no double-write risk).
- No pg_cron dispatch of the three new jobs has been observed yet in monitoring.dispatch_log.
- After merge: `pipelines/audit_monitoring_coverage.py` will see the manifest entries
  for the new pg_cron jobs, and GAP-GHA-SCHEDULES will be fully closed.
