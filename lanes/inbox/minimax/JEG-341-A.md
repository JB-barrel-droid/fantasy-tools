# JEG-341-A — Delivery Report

**Lane:** minimax (M3)
**Branch:** `minimax/jeg-341a-arch-target` (already checked out)
**Date:** 2026-10-03

## What was written

- **`docs/architecture-target.md`** — new. Codifies the five-layer architecture proposed by the JEG-341 review:
  1. **Raw / Source** — source-native ingested data, provenance preserved byte-for-byte.
  2. **Normalized / Core** — canonical entities / keys and normalized source observations.
  3. **Derived / Model** — consensus, projections, trade values, adjusted values.
  4. **Serving / API** — small versioned product read surfaces (`api.player_values`, `api.players`, `api.player_context`, `api.product_options`, `api.product_snapshot` per `docs/contract/fe-read-contract-v1.md`).
  5. **Ops / Monitoring** — pipeline state, freshness, run history, failures.

  For each layer the document records: what belongs there, who/what writes to it, allowed dependency direction, and current repo locations (tables / dirs / files). A full ASCII dependency diagram is included as §5.1. Hard-constraint self-check is §7; open questions are §6.

## Repo locations mapped to each layer

### Layer 1 — Raw / Source
- `data/raw/sources/<source>/...` (versioned bake snapshots)
- `data/inputs/ecr_draft.json`
- `data/inputs/espn_pies.json`
- `data/inputs/prediction_markets_season.csv`
- `data/inputs/espn_projections.csv`
- `data/inputs/cbs_*.json`, `data/inputs/razzball_projections.csv`
- Supabase: `public.source_trade_values`, `public.espn_*`, `public.cbs_ros_projections`, `public.razzball_projections`, `public.fp_*`

### Layer 2 — Normalized / Core
- Supabase `public.players` (canonical naming table)
- `data/fixtures/current/players.json` (pinned export)
- `data/fixtures/current/players.naming-manifest.json`
- Supabase `public.player_identities`, `public.player_identity_aliases`
- `output/reviewed/...` (review rows)
- Supabase `public.fp_season_projections`, `public.fp_season_latest_norm`, `public.season_actuals_ytd`, `public.games`, `public.player_value_notes`
- `pipelines/import_supabase_references.py::_select_latest_bake` (single choke point per pipeline-rules §7a)

### Layer 3 — Derived / Model
- Supabase `public.consolidated_values` (8-col PK + `view`; backing for `api.player_values`)
- `data/ddf-two-tier/ddf-<date>-<source>-<scoring>-<teams>-0p15/...`
- `data/adjustment-inputs/{adjustment-inputs.json, jeg242-blend-controls-v1.json, adjustment-inputs-stage1-empty.json}`
- `data/fixtures/current/comparison-sources-data.json` (active)
- `data/fixtures/current/sources_data.json` (full, 11 sections)
- `data/reference/...`
- `dist/modules/{cross-source-agreement, scale-agreement, source-fidelity, identity-verification, data-accuracy, chart-input-coverage, index-math, source-value-lineage, espn-input-comparison, espn-raw-values, player-trace, aggregate-diagnostics}.json`
- `pipelines/build_*` (the derived-layer builders)

### Layer 4 — Serving / API
- `sql/contract/api_v1.sql` (contract DDL)
- `sql/consolidated_values.sql`, `sql/migrations/...`
- Supabase `api.*` schema (5 surfaces per `fe-read-contract-v1.md` §2)
- Frontend entry: `app/trade-value-chart/assets/{curve-widget,comparison-dashboard}.{js,css}`, `index.html`
- Monitor: `modules/{consolidation,dashboard}.html`

### Layer 5 — Ops / Monitoring
- `output/comparison-chain-status.json`
- `output/source-import-health.json`, `dist/modules/source-import-health.json`
- `output/pipeline-checkpoints.json`, `dist/modules/pipeline-checkpoints.json`
- `dist/modules/{data-accuracy, github-actions, live-page-scrape}.json`
- `.github/workflows/{rebuild-chain, espn-supabase-sync, cbsros-supabase-sync, fantasycalc-drift, player-trace-rebuild, source-vintage-check, pages, preview, live-page-synthetic}.yml`
- `tests/rendered_gate/gate.mjs`, `rendered-gate.json`
- `docs/{pipeline-rules, watchdog, import-health-schema, risk-register, claude-log}.md`

## Items marked AMBIGUOUS

1. **`data/inputs/player_identity_map.json`** (§1) — straddles raw/normalized. Pre-canonical identity map produced by a scraper-side pass; the normalized layer must re-validate against rule §2 (fail-closed).
2. **`data/raw/sources/<source>/...` versioned snapshots** (§3) — directory convention says raw; post-`_select_latest_bake` identity says normalized. Treated as "raw-with-applied-provenance"; downstream readers may not skip the normalization step.
3. **`dist/assets/comparison-sources-data.json` and `dist/assets/player-news.json`** (§4) — derived-layer bytes consumed as serving surfaces today; transitional until the `fe-read-contract-v1.md` rollout lands.
4. **`dist/assets/reference-freshness.json`** (§5) — lives in dist tree (looks serving-like); is actually an ops/monitoring artifact consumed by the freshness gate.

## Confirmation: all Q1–Q8 carried as open questions

All eight questions are listed unresolved in §6 of `docs/architecture-target.md`:

- **Q1** — browser-side adjustment fit
- **Q2** — Vegas definition (raw leg, normalized section, or out of chart entirely; pipeline-rules §7 already rules out the comparison-source path)
- **Q3** — fixed-pie anchor (still ESPN per pipeline-rules §3, but the reindex-anchor question is open)
- **Q4** — Tier-2 scope (today: ESPN / CBS ROS / Razzball only)
- **Q5** — VORP glossary (user-facing term is locked to "value above waivers" per pipeline-rules §6; richer copy is open)
- **Q6** — JEG-322 family scope (parked per `fe-read-contract-v1.md` §1.2; `view='vorp_on_demand'` reserved as future extension)
- **Q7** — Supabase system-of-record scope (extends to which derived tables?)
- **Q8** — `dist/assets/*.json` transitional serving shape (codify or accelerate the migration)

None of Q1–Q8 are resolved in the document.

## Hard-constraint compliance

- **No methodology changes** — `docs/pipeline-rules.md` was not edited; only referenced.
- **No new user-facing copy claims** — only the approved terms **Data Driven Football**, **DDF methodology**, **Vegas**, and **value above waivers** appear.
- **Q1–Q8 unresolved** — all eight carried forward in §6.
- **No other source files edited** — `git status` shows only the two new files below.

## Next step (not done in this session)

Commit on the current branch with message `JEG-341-A: architecture-target.md five-layer codification (draft, open questions carried)`. Do NOT merge, push, or deploy.