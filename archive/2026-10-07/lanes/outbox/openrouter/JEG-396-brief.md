# Brief: JEG-396 — freshness SLA design for the weekly dashboard load

## Task
Design the freshness monitoring and alerting for the weekly dashboard load.
Output a concrete implementation plan (workflow YAML additions + Supabase
SQL for the checks). No DDL on prod tables; the checks must be read-only
SELECTs suitable for pg_cron or a GitHub Actions step.

## Context
- Loader: `pipelines/load_weekly_dashboard.py` (idempotent; NOOP when the
  current run already covers the bundle; fail-closed exit 2).
- Scheduler: `.github/workflows/weekly-dashboard-load.yml`, daily 16:07 UTC
  (11:07 CT), LIVE. Standing direction: as much as possible in Supabase
  (pg_cron), minor assistance from GitHub Actions, never the Muse runtime.
- The morning refresh pipeline publishes the canonical bundle to
  `data/weekly/` in the repo (contract from JEG-399); the workflow loads the
  newest bundle found there.
- Status view `api.weekly_dashboard_status` is being designed separately
  (JEG-397) — assume it will expose published season/week, bundle_built_at,
  run_created_at, signal_count, has_current. Design against that interface,
  and note anything it must include for your checks to work.

## Requirements
1. Staleness definition: precise rules for when the dashboard counts as
   stale (current-run age vs expected week; bundle_built_at vs now;
   repeated NOOP on an outdated bundle). Handle the Monday-night week
   rollover and the CST/CDT transition (workflow cron is UTC — state the
   exact UTC times for both).
2. Check implementations: read-only SQL queries (for pg_cron) that detect:
   refresh-to-publication lag, current-run age beyond threshold,
   expected-week mismatch (compute expected NFL week from date — state the
   rule), failed/zero current runs, repeated NOOP on an outdated bundle.
3. Alerting: for each check, what fires, where it goes, and what the
   on-call action is. Prefer Supabase-native (pg_cron + a health table +
   webhook) with GitHub Actions as fallback; justify the split.
4. Failure semantics: a failed load must leave the prior current run serving
   (already true — say how the checks confirm it) with honest timestamps.

## Output
- The staleness rules as a table (condition → severity → action).
- The SQL checks, each with its alert threshold.
- Workflow YAML additions (if any) as a diff.
- What JEG-397's status view must expose for this to work (explicit list).
