# Weekly dashboard freshness runbook (JEG-396)

## What "fresh" means
The dashboard is fresh when `api.weekly_dashboard_status` shows `has_current=true`
and the published `(season, week)` matches the expected NFL week for today.

## Staleness rules

| # | Condition | Severity | Action |
|---|-----------|----------|--------|
| S1 | `bundle_built_at` > 8 days old | Warning | Check the morning refresh pipeline's health; no pager |
| S2 | Published week ≠ expected week from Wednesday 05:59 UTC | Critical | Rerun the `weekly-dashboard-load` workflow; if it NOOPs, the bundle in `data/weekly/` is stale — investigate the upstream pipeline (JEG-399) |
| S3 | `has_current = false` (no current run) | Critical | Do NOT publish blindly. Inspect `weekly_dashboard_runs` for the newest non-current run; promote manually via `promote_weekly_dashboard_run(run_id, signal_count)` only after verifying its signals |
| S4 | Repeated NOOPs while published week ≠ expected | Critical | The loader is "succeeding" on a stale bundle — the worst silent state. Investigate upstream |
| S5 | Newest run > 8 days old | Critical | The loader isn't running — check the workflow schedule / Actions status |
| S6 | `signal_count = 0` on the current run | Warning | Data-quality flag; do not republish until understood |

## Expected-week rule
NFL weeks are labeled by the Sunday ending the week. Anchor: 2026 season week 1
began Thursday 2026-09-10. `expected = 1 + floor((today - 2026-09-10) / 7)`.
Monday/Tuesday tolerate `expected - 1` (Monday-night games may just have
concluded); from Wednesday the current week must be published.

**Annual maintenance (every August):** bump `SEASON`, `CONTENT_WEEK_1_START`
and `GAME_WEEK_1_START` in `pipelines/nfl_week.py` (the one week calendar;
this check uses its game week). Without the bump, S2 fires false positives all season.

## Where checks run
- **GitHub Actions (live now):** the `weekly-dashboard-load` workflow runs
  `scripts/check_weekly_freshness.py` after every load with `if: always()`.
  Breaches surface as workflow annotations + a failed step.
- **Supabase-native (follow-up):** pg_cron job querying the same status view
  and posting critical breaches to the on-call webhook. Needs an on-call
  webhook URL before it can be wired — tracked on JEG-396.

## Failure semantics
A failed load never unpublishes the dashboard: promotion happens only inside
`promote_weekly_dashboard_run`, which refuses on count mismatch or regression.
After a failure, `has_current` still points at the prior good run with honest
timestamps — the checks above confirm exactly that.
