# Current Architecture

Last updated: 2026-10-12 (JEG-599). Replaces the 2026-09-19 Muse-migration page; the old page, the dependency map and the migration docs are in `archive/` (see its README). The target state is `docs/architecture-target.md`. Pipeline stage shape is `docs/modular-pipeline.md`; standing rules are `docs/pipeline-rules.md`.

## What it is

A static site on GitHub Pages (`dist/`) with no login and no server. All numbers are baked into JSON by scheduled jobs and committed to the repo; the browser computes only layout and the roster-dependent value math (`app/trade-value-chart/assets/value-model.js`). Supabase is the system of record for scraped source data and monitoring history, not a runtime dependency of the site.

```text
sources -> Supabase (save_* / pull_* jobs) -> rebuild-chain (import -> per-source sections -> validate)
        -> committed fixtures (data/fixtures/current) -> make sync -> dist/ -> Pages deploy
```

## Files the site reads, and the job that writes each

| File served | Read by | Written by |
|---|---|---|
| `index.html` (the v2 front door at the site root since 2026-10-08) and `v2/` assets | visitors | `pipelines/build_v2_page.py` via `make sync`; source in `app/v2/`; it reads the engine page built from `app/trade-value-chart/` (`build/engine/`, never uploaded) whose inline `players-data` JSON comes from `data/fixtures/current/players.json`, baked by `pipelines/bake_players.py` in the rebuild-chain job (or manually via `bake-players.yml` on a `bake/**` branch) |
| `assets/comparison-sources-data.json` | chart, comparison table, `/v2/` | `pipelines/rebuild_comparison_chain.py` (rebuild-chain job) promotes sections into `data/fixtures/current/comparison-sources-data.json`; `make sync` copies it |
| `assets/reference-freshness.json` | freshness labels | `make sync` (`check_reference_freshness.build_report`) |
| `assets/history/index.json` and per-week files | week history views | `pipelines/build_week_history.py`, run by `make sync` and captured in rebuild-chain |
| `consolidated-values.json` | consolidated value consumers | `make sync` (`write_consolidated_export`) from the Supabase `consolidated_values` table, which rebuild-chain fills via `pipelines/build_consolidated_values.py` |
| `classic/` | old links; redirects to the root | `make sync` |
| `modules/*.json` and `modules/*.html` (ops and fidelity pages) | internal monitors only, not linked publicly | see "Monitoring files" below |

Per-source legs the chain builds from live in `data/ddf-two-tier/` (committed by rebuild-chain). Raw scraped snapshots live under `data/raw/` and are gitignored.

## Jobs

Scheduling is owned by Supabase pg_cron, which dispatches the GitHub workflows (`supabase/migrations/gha_schedules_pg_cron.sql` and the later schedule migrations). Checked 2026-10-12 with a read-only query of `cron.job`: 19 jobs, all active.

| pg_cron job (schedule UTC) | Workflow / effect |
|---|---|
| `vintage-check-live` (hourly :00) | `source-vintage-check.yml`: dispatches rebuild-chain only when stored source vintage differs from the fixture |
| `rebuild-chain-bake-live` (daily 11:45) | `rebuild-chain.yml` with ESPN re-bake of players.json |
| `pages-deploy-live` (daily 11:30) | `pages.yml`: `make sync`, `make validate`, rendered gate, deploy |
| `source-probe-fantasycalc` (hourly :05), `source-probe-projections` (every 4h), `source-probe-trade-charts` and `-weekend` | `source-probe.yml`: cheap change probes that trigger the matching ingest |
| `espn-weekly-store-live` (12:40 daily) and `-sunday` | `espn-weekly-store.yml` |
| `player-status-history-live` (13:10 daily) and `-sunday` | `player-status-history.yml` |
| `trigger-fantasycalc-weekly-save` (Tue, Fri 13:07) | `fantasycalc-weekly-save.yml` |
| `trigger-player-trace-live` (12:47 daily) | `player-trace-rebuild.yml` |
| `sleeper-identity-refresh-live` (Tue, Thu 09:17), `player-identity-reconcile-nightly` (07:30) | identity workflows |
| `fidelity-pulse-live` (every 3h :40) | `fidelity-pulse.yml` |
| `health-artifacts-live` (every 6h :50), `live-page-synthetic-live` (12:15) | monitoring artifacts and live page checks |
| `cron-retention-30d` (03:00) | trims cron run history |

Ingest workflows not on a pg_cron row (`espn-supabase-sync.yml`, `cbsros-supabase-sync.yml`, `razzball-supabase-sync.yml`, `trade-chart-ingest.yml`, `nflverse-history-load.yml`) are dispatched by the probes or by hand. `rebuild-chain.yml` has no fixed schedule of its own.

### What rebuild-chain does

1. Import fresh snapshots from Supabase (`import_supabase_references.py`), run the import health check.
2. Optionally re-bake `players.json` (daily ESPN anchor refresh).
3. For each source: match, reference, section, reindex, review, promote. A single-source failure or review hold keeps that source's last promoted section (per-source isolation); the other sources publish. Every source failing, or a failure in the shared re-index and rank-guard stage, fails the chain.
4. Engine vs Python reference value check (`value_check.py`) and fidelity hold (`fidelity_hold.py`) hold disagreeing sources with a `validationHold`.
5. `make validate` runs inside the chain; red means nothing is committed except status files.
6. Build the consolidation layer, commit fixtures and status, then trigger the Pages deploy.

## Monitoring files

`modules/status.html` is the ops page (see `SYSTEM_MAP.md`). It reads only published JSON: `monitoring-summary.json`, `source-import-health.json`, `pipeline-checkpoints.json`, `ops-status.json` (health-artifacts job), `comparison-chain-status.json` and `github-actions.json` (rebuild-chain), `fidelity-pulse.json` (fidelity-pulse job), `value-check.json`, `rank-guard.json`, `source-divergence.json`, `input-lineage.json` (rebuild-chain or `make sync`). `modules/dashboard.html` and `modules/consolidation.html` are detail pages.

## What Supabase is for

- Store of scraped source rows (`espn_season_projections`, `cbs_ros_projections`, `razzball_projections`, `source_trade_values`, `cbs_trade_values`, `bakes`) that the chain imports.
- Canonical identity (`players.player_key`, `player_name_aliases`, `external_id_map`); unmatched or ambiguous players stay unmatched, missing values stay null.
- Weekly history stores (`player_game_stats`, `projection_snapshots`, `player_status_history`, `nflverse_*` history).
- The consolidation layer (`consolidated_values`) and monitoring history (`fidelity_*`, `value_check_*`, `source_probe_*`, `pipeline_write_audit`).
- Production writes need explicit approval. The table-by-table map is `docs/supabase-tables.md`.

## Retired (do not describe as current)

Muse hosting and the ts-spaces artifact, the multi-LLM lanes, the waiver-wire and weekly-vegas products (stubs only so `make sync` still copies them), weekly signals, the bias-correction fit and `*_adjusted` fixture sections (JEG-539), and the ECR feed. Their code and docs are in `archive/`.

## Not verified here

The file-to-job table was assembled from `sync_dashboard_artifacts.py`, the workflow files and the pg_cron migrations on 2026-10-12; no live run was traced end to end for this edit.
