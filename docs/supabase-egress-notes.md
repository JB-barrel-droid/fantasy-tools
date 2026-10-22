# Supabase egress notes (JEG-793)

Purpose: find which reads cost the cloud project's egress (Free is 5 GB per
month, Pro 250 GB). Status 2026-10-21: steps 1 to 3 of JEG-793 only. Nothing
below has been measured yet. Every figure in "Inferred" is read from code and
workflow files, not from a run. No workflow schedule or read pattern was changed.

## How to read the measured numbers (MEASURED, after the counter ships)

`pipelines/gh_sbclient.py` counts response body bytes and request counts per
`(method, table or rpc/<function>)`, including error bodies. It prints when
`SUPABASE_BYTES_LOG=1` or `GITHUB_ACTIONS=true`, once at process exit.

- stderr, one line per table, largest first:
  `[supabase-bytes] <workflow> GET <table> requests=<n> bytes=<n>`
- A markdown table in the job's Step Summary (`$GITHUB_STEP_SUMMARY`), headed
  `Supabase response bytes (<workflow>, total N)`.
- Each Python process prints its own block, so a workflow with several scripts
  shows several blocks; add them per workflow. `bytes` is the decoded body that
  Python read. PostgREST sends JSON uncompressed unless gzip is negotiated, and
  urllib does not ask for gzip, so this should match wire egress closely (not
  yet confirmed against the Supabase dashboard; compare once).
- Row data, query params and keys are never logged.
- Collect: `gh run list --workflow <name> --limit 50`, then
  `gh run view <id> --log | grep supabase-bytes`. Rank by summing `bytes` per
  workflow over a day, multiplied by runs per day from the table below.

Gap: some readers do not go through `gh_sbclient`. Anything that imports a
different `sbclient` (Muse, or the Mac self-host path) is uncounted, and the
Edge Functions and the Pages site's browser reads (if any hit Supabase) are not
covered. The Supabase dashboard egress graph stays the cross-check.

## Triggers (INFERRED from code)

Almost every `schedule:` in `.github/workflows/` is commented out. The real
clock is pg_cron in `selfhost/migrate/cron_and_functions.sql` (20 jobs), which
calls `dispatch_gha_workflow(...)`. Two workflows chain on `workflow_run`:
fidelity-pulse after the rebuild chain, record-pages-deploy after a Pages
deploy. The cloud project's own pg_cron list was not inspected, so confirm it
matches this file.

| Workflow | pg_cron schedule (UTC) | Runs/day |
|---|---|---:|
| source-vintage-check | `0 * * * *` (via `dispatch_vintage_check`) | 24 |
| source-probe fantasycalc | `5 * * * *` | 24 |
| source-probe espn,cbsros,razzball | `25 3-23/4 * * *` | 6 |
| source-probe cbs,usatoday,fantasypros | `35 */3 * * 1-4`; `35 0,12 * * 0,5,6` | 8 (Mon-Thu), 2 (Fri-Sun) |
| source-probe draftsharks,fantasysharks | `45 4,16 * * *` | 2 |
| fidelity-pulse | `40 */3 * * *` | 8 |
| health-artifacts | `50 */6 * * *` | 4 |
| rebuild-chain (bake) | `45 11 * * *` | 1 |
| rebuild-chain (probe-driven) | dispatched by probes/vintage on change | unknown |
| pages (Deploy dashboard) | `30 11 * * *` | 1 |
| player-trace-rebuild | `47 12 * * *` | 1 |
| live-page-synthetic | `15 12 * * *` | 1 |
| player-identity-reconcile | `30 7 * * *` | 1 |
| espn-weekly-store | `40 12 * * *`; `20 16 * * 0` | 1, plus Sun |
| player-status-history | `10 13 * * *`; `30 16 * * 0` | 1, plus Sun |
| fantasycalc-weekly-save | `7 13 * * 2,5` | 2 per week |
| sleeper-identity-refresh | `17 9 * * 2,4` | 2 per week |

Probes that find a change dispatch the matching `*-supabase-sync` save and
the rebuild chain; how often that happens is data dependent, so the chain's
daily run count is the main unknown.

## Reads by workflow (INFERRED: tables read, pagination, column pruning)

`get_all` pages 1000 rows at a time with `order=id`, so it downloads the whole
filtered table; `get(..., limit=1)` is one small page.

| Workflow | Script and call | Table | Shape |
|---|---|---|---|
| fidelity-pulse | `fidelity_pulse.py` `SupabaseStore.rows` (line ~618) | `source_trade_values` / `cbs_trade_values` | `get_all`, select listed columns, one source+week, per source |
| fidelity-pulse | `snapshot_rows` (line ~631) | each projection source's `STORED_TABLE` | `get_all`, one snapshot, listed columns |
| fidelity-pulse | `latest_week`, `latest_snapshot`, `probe_state` | same tables, `source_probe_state` | `limit=1` and a one-row read |
| source-vintage-check | `check_source_vintage.py` via `verify_import_health` | `source_trade_values`, `espn_season_projections`, `cbs_trade_values`, `cbs_ros_projections`, `razzball_projections` | `get_all` of a few columns (`player_key,...dates`) for the latest week/snapshot; no `select=*` |
| rebuild-chain | `import_supabase_references.py` (3 `get_all`) | `source_trade_values`, `espn_season_projections`, `cbs_trade_values`, `cbs_ros_projections`, `razzball_projections` | `select=*`, per source, as_published; the widest reads in the repo |
| rebuild-chain | same script | `players` | `get_all` with `player_key=in.(...)` for names and positions |
| rebuild-chain | `build_consolidated_values.py:480` | `players` | `get_all`, `select=player_key` |
| rebuild-chain | `bake_players.py` `query_all` | `teams`, `games`, `players` | `get_all` (columns not checked) |
| rebuild-chain | `check_espn_bake_csv.py` | `espn_season_projections` | `limit=1` |
| rebuild-chain | `verify_import_health.py`, `production_verify.py:151` | per verified table | `production_verify` uses `select=*` on whole tables |
| rebuild-chain | `build_week_history.py:360-377` | week-history tables | manual paging, selected columns |
| rebuild-chain | `load_value_check.py` | `value_check_runs`, `value_check_values` | writes only (value_check_values is never read) |
| source-probe | `source_probe.py:723` | `source_probe_state` | `select=*`, tiny |
| health-artifacts | `import_supabase_references`, `verify_import_health`, `build_monitoring_summary` (`player_name_aliases`), `build_ops_status` | same reference tables, aliases | `select=*` references again, 4 per day |
| player-identity-reconcile | `reconcile_player_identity.py` (3 `get_all`) | `players`, aliases, queue | `get_all` |
| sleeper-identity-refresh | `sync_sleeper_players.py` | `players` | `get_all` x2 |
| espn-weekly-store, player-status-history | `export_weekly_store.py`, `save_espn_weekly.py`, `save_player_status_history.py` | weekly tables | `get_all` |
| *-supabase-sync saves | `save_*_references.py` | their source tables | `get_all` (dedupe/exists checks), only on change |
| fantasycalc-drift | `import_supabase_references.py` | `source_trade_values` | `select=*` |

## Candidate hogs, ranked by reasoning only (INFERRED, to be confirmed)

1. rebuild-chain `import_supabase_references` `select=*` reads. Full width, and
   history-bearing tables (`source_trade_values` grows per bake). Run count per
   day is the unknown.
2. health-artifacts running the same importer 4 times a day.
3. fidelity-pulse, 8 per day: narrowed to one week or snapshot and chosen
   columns, so likely smaller than the JEG-793 hypothesis, but it multiplies by
   source count.
4. source-vintage-check, 24 per day: columns pruned and latest-week only, so
   small per run; the count is what hurts.
5. `production_verify.py` `select=*` full-table reads, if it runs in CI.

This ordering contradicts the ticket's "fidelity-pulse is the likely hog" only
as a hypothesis; confirm or refute with the measured table above before acting.
Step 3b options (less frequent pulse, `_written_at` incremental reads, column
pruning, caching, archiving) are not started and need a separate decision.

## Not covered

- Write-side payloads (request bytes) are not counted; egress is responses.
- The migration 014 retention change is applied on the Mac copy only, not on
  the cloud project (needs Jeremy's approval).
