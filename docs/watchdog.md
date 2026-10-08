# Source producers and schedules

Every job that pulls a source and writes it to Supabase, who schedules it, and
how it proves it ran. Rewritten 2026-10-08 (producers lane); this file used to
describe the Muse-era source-pull watchdog, which is retired (see the end).

Rules that hold for every producer:

- **pg_cron is the only scheduler.** Each producer is a GitHub Actions workflow
  with no `schedule:`; a Supabase pg_cron job dispatches it through
  `public.dispatch_gha_workflow(<workflow>, <inputs jsonb>)`. One owner, so a
  schedule change is one SQL statement.
- **Producers only write source tables.** Publishing is the rebuild chain's job
  (`rebuild-chain-live`, every 6 h at :17; `rebuild-chain-bake-live` 11:45 UTC
  also re-bakes players.json). A producer that misses a day leaves the last good
  data in place; the chain keeps publishing it under its own vintage.
- **Every producer records its run** in `monitoring.check_observations` (write
  mode only). `config/monitoring_coverage.json` maps workflow -> pg_cron job ->
  check; `tests/test_monitoring_coverage.py` enforces it.
- **Dry runs are free.** Dispatching any producer without its write input (or
  pushing to its `*/dry-*` branch) pulls, resolves and validates without writing.

Per-source cadence and retry slots are owned by the refresh-cadence lane
(`feat/refresh-cadence`); the table below is the state on 2026-10-08.

## Producer table (live state, read from `cron.job` 2026-10-08)

| Source | pg_cron job | When (UTC) | Workflow (entry point) | Write inputs | Writes | Monitored check |
|---|---|---|---|---|---|---|
| ESPN projections | `trigger-espn-sync-live` | daily 11:30 | `espn-supabase-sync.yml` | `{}` (writes unless `dry_run: true`) | ESPN tables | `espn_supabase_sync` |
| Razzball ROS | `razzball-sync-live` | daily 11:20 | `razzball-supabase-sync.yml` | `{"mode": "write"}` | `public.razzball_projections` | `razzball_projections_sync` |
| CBS ROS | `trigger-cbsros-sync-live` (+ `trigger-cbsros-sync-retry` 17:00 if no row today) | Wed 11:00 | `cbsros-supabase-sync.yml` | `{}` | `public.cbs_ros_projections` | `cbsros_supabase_sync` |
| CBS trade chart, USA Today, FantasyPros | `trade-chart-ingest-live` | daily 12:07 | `trade-chart-ingest.yml` (matrix cbs / usatoday / fantasypros) | `{"mode": "write"}`; optional `source` (`cbs`, `usatoday`, `fantasypros`, `both`) and `week` | `public.source_trade_values` (cbs: its table) | `cbs_trade_chart_ingest`, `usatoday_trade_chart_ingest` (FantasyPros not recorded) |
| FantasyCalc | `trigger-fantasycalc-weekly-save` | Tue + Fri 13:07 | `fantasycalc-weekly-save.yml` | `{"mode": "write"}` | `public.source_trade_values` bake `fcwk<week>_<date>_v1` (12 teams, 1 QB, 3 scorings; `value` reindexed, `native_value` raw) | `fantasycalc_weekly_save` |
| Sleeper identity | `sleeper-identity-refresh-live` | Tue + Thu 09:17 | `sleeper-identity-refresh.yml` | `{}` | identity base | `sleeper_identity_refresh` |

Downstream, not producers: `rebuild-chain-live` (6-hourly :17),
`rebuild-chain-bake-live` (11:45), `pages-deploy-live` (11:30),
`trigger-player-trace-live` (daily 12:47 after
`producers_schedule_tidy_20261008.sql`; served monitor page),
`vintage-check-live` (hourly).

Manual only (no pg_cron job): `fantasycalc-drift.yml` (has FantasyCalc moved
since the last save?), `weekly-dashboard-load.yml` (Weekly Signals, paused,
JEG-399), `bake-players.yml`, `cbsros-consolidation-load.yml`.

Dispatch by hand (integrator; production writes):

```
gh workflow run fantasycalc-weekly-save.yml -f mode=write
gh workflow run trade-chart-ingest.yml -f mode=write -f source=usatoday
gh workflow run razzball-supabase-sync.yml -f mode=write
gh workflow run espn-supabase-sync.yml
gh workflow run cbsros-supabase-sync.yml
```

## USA Today fetch chain

usatoday.com answers GitHub-hosted runners with HTTP 402 ("Access
Restricted"); the gannett-cdn sitemaps still answer, so discovery works from
CI. The article fetch (`ops/watchdog/pull_usatoday.py: fetch_article`) is:

1. **Direct.** Any status other than 401/402/403/429 is returned as is.
2. **Supabase relay** (primary fallback): Edge Function `usatoday-fetch`,
   called with the existing `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` secrets.
   Supabase egress is not walled (Week 5 ingested through it, 2026-10-07).
3. **Firecrawl** (optional): only when the `FIRECRAWL_API_KEY` repo secret
   exists; the workflow maps it into the Ingest step. Empty secret = skipped.
4. **SOURCE_BLOCKED.** A fallback counts only if it returns 200 *with the
   chart's table markup*; a 200 interstitial falls through to the next one.
   When none succeeds the run fails with `SOURCE_BLOCKED ... (fallbacks:
   supabase relay=..., firecrawl=...)`, recorded as error code
   `SOURCE_BLOCKED` on the warn-level `usatoday_trade_chart_ingest` check. The
   last good week stays published.

Pinned by `tests/test_trade_chart_ingest_ci.py` (UsatSourceBlockedFallbackTests).

## Failure path

When a producer's check goes red: read the run's annotations (the ingest
steps surface their log tail as `::notice`/`::error`), check whether the
source URL or markup changed, run the producer in dry mode on a branch to
reproduce, fix the pull code, re-run in write mode. Escalate to Jeremy only
when it cannot be fixed (what broke, what was tried, what is needed).

## Muse-era jobs (disabled 2026-10-06) and what replaced them

| Muse job | Outcome |
|---|---|
| razzball-projections-pull | Replaced: `razzball-supabase-sync.yml` + `razzball-sync-live`. |
| cbs / usatoday trade-chart ingest | Replaced: `trade-chart-ingest.yml` + `trade-chart-ingest-live`. |
| FantasyCalc weekly save | Replaced: `fantasycalc-weekly-save.yml` + `trigger-fantasycalc-weekly-save`. `ops/watchdog/refresh_fantasycalc.py` (24-combo Muse refresher) and `pipelines/refresh_fantasycalc_supabase.py` (wrote raw natives into `value`) deleted 2026-10-08. |
| prediction-markets-pull | Retired 2026-10-08 with the leg: no page read its fields; input `data/inputs/prediction_markets_season.csv` (frozen 2026-09-22) deleted, `bake_players.py` no longer bakes `pm_*`. |
| nflverse-weekly-refresh | Retired: only the archived Weekly Vegas / waiver-wire code (`archive/2026-10-07/`) read nflverse; nothing live does. |
| fantasy-lineup-risk-dial | Retired: no code in this repo references it (Weekly Signals tool, paused). |
| source-pull-watchdog | Retired 2026-10-08: `ops/watchdog/pull_watchdog.py` graded files on Muse's machine and `make watchdog` is gone. Superseded by `monitoring.check_observations` from each CI producer. Its tests of the live pullers moved to `tests/test_trade_chart_pullers.py`. |
