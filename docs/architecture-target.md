# Architecture Target (Five-Layer Codification)

**Ticket:** JEG-341-A (follow-up to JEG-341 review)
**Status:** DRAFT. Structural only. Methodology contracts in `docs/pipeline-rules.md` are preserved verbatim; no values, scaling, or user-facing copy are changed by this document.
**Date:** 2026-10-03
**Scope:** Where data and code belong. Not what the math is.

## 0. What this document is and is not

This document codifies the **five architectural layers** the JEG-341 review proposed and assigns the repo's current artifacts to them. It is **structural**:

- It does **not** change the methodology contracts in `docs/pipeline-rules.md` (canonical identity via naming table, null-not-zero, content-vintage-not-pull-time, fail-closed matching, versioned bakes).
- It does **not** introduce new user-facing copy. The only approved user-facing brand terms are **"Data Driven Football"** and **"DDF methodology"**; the market side is **"Vegas"**; the value-above-waivers concept is called **"VORP vs waivers"** in user-facing text (decision copy-vorp-001, 2026-10-06), and no other VORP wording is allowed.
- It does **not** resolve the open questions raised by the JEG-341 review (Q1–Q8). Those are carried forward unresolved in §6 for Jeremy.
- It does **not** edit any code, schema, fixture, or pipeline script.

The dependency rule that this whole target obeys is one-directional. Each layer may **read** the layers below it, and **write** only to its own layer or to layers above it via the documented promotion path. No layer reaches sideways; no layer reaches backward. The full diagram is in §5.

---

## 1. Layer 1 — Raw / Source

**Purpose:** Hold source-native ingested data exactly as the source published it, with provenance preserved byte-for-byte. This is the only layer where source content can be read back unchanged.

### What belongs here

- Raw scraper dumps per source (publisher-native row shape, not yet matched to the canonical naming table).
- Supabase-stored scraped references (per `docs/pipeline-rules.md` §7), one immutable versioned bake per source-pull, content vintage stamped from the publisher's `content_vintage`.
- Raw inputs that have not yet been validated against the canonical naming table (fail-closed matching has not yet been applied).
- ECR draft pull, ESPN pies, prediction-markets CSV, ESPN/CBS projections — all in publisher-native shape.

### Writers

- **Scrapers / saver scripts** (e.g. the ESPN, USA Today, FantasyCalc, FantasyPros, CBS, CBS ROS, Razzball saver scripts under `pipelines/`).
- **Supabase writer path** for scraped references (`make supabase-import` is the read path; the writers behind it are the only allowed writers here).

### Readers

- Only the **normalization stage** (§2). Nothing else may read raw; specifically, the serving layer and the frontend must never read raw directly.
- **Ops/monitoring** (§5) reads raw provenance metadata (e.g. `content_vintage`, `source_provenance`) but never raw values.

### Dependency direction

```
raw  →  normalized (only)
```

### Current repo locations

| Artifact | Path | Notes |
|---|---|---|
| Supabase scraped reference tables | `public.source_trade_values`, `public.espn_*`, `public.cbs_ros_projections`, `public.razzball_projections`, `public.fp_*` (per `docs/architecture-current.md` §Supabase) | Backend-of-record for scraped references. Versioned bakes live here. |
| Raw scraper snapshots | `data/raw/sources/<source>/...` (per `docs/pipeline-rules.md` §7) | The on-disk mirror of the import stage; versioned by `content_vintage`. |
| ECR draft pull | `data/inputs/ecr_draft.json` | ECR is a leg source, not a comparison source. Raw-only. |
| ESPN pies | `data/inputs/espn_pies.json` | Source-native pie totals; never baked into comparison outputs. |
| Prediction markets CSV | `data/inputs/prediction_markets_season.csv` | "Vegas" leg input. Raw-only. |
| ESPN/CBS/Razzball raw projections | `data/inputs/espn_projections.csv`, `data/inputs/cbs_*.json`, `data/inputs/razzball_projections.csv` | Publisher-native shape. |
| `player_identity_map.json` (build identity) | `data/inputs/player_identity_map.json` | **AMBIGUOUS** — see note below. |

**AMBIGUOUS:** `data/inputs/player_identity_map.json` straddles the raw/normalized boundary. It is a pre-canonical identity map produced by a scraper-side pass, but it carries a shape closer to a normalized identity table than a raw scrape. Treat as raw-with-derived-key-claim; the normalized layer must re-validate it (rule §2 of `docs/pipeline-rules.md`).

---

## 2. Layer 2 — Normalized / Core

**Purpose:** Hold the canonical identity authority and the source observations **after** fail-closed identity matching and normalization. This is where `player_key` resolution happens and where source observations become comparable.

### What belongs here

- The canonical naming table itself (`players` / `player_key` / `full_name`) and its pinned fixture export.
- Normalized source observations keyed on the canonical `player_key`, with the **null-not-zero** rule and **content-vintage-not-pull-time** rule already applied.
- Identity aliases and review rows (`review_rows`, `player_identity_aliases`).
- The naming manifest pinning the fixture's identity projection to its `supabase:players` source.

### Writers

- **The naming-fixture pin script** (`pipelines/pin_naming_manifest.py`) — writes `players.json` and `players.naming-manifest.json` atomically.
- **Normalization / matching stages** that resolve source observations onto canonical `player_key` (fail-closed: unmatched / ambiguous / position-conflicting → `review_rows`, never guessed).
- The Supabase-side canonical-naming writer (the system of record for `players`; scope of that role is **AMBIGUOUS** — see Q7 in §6).

### Readers

- **Derived/model** layer (§3) reads normalized observations.
- **Serving/api** layer (§4) reads canonical identity and `players` for `api.players` lookups.
- **Ops/monitoring** layer (§5) reads `review_rows` counts and naming-manifest hashes.

### Dependency direction

```
raw       →  normalized
derived   →  normalized (consumes canonical keys)
serving   →  normalized (reads canonical identity)
```

### Current repo locations

| Artifact | Path | Notes |
|---|---|---|
| Canonical naming table | Supabase `public.players` (per `docs/pipeline-rules.md` §1) | The single naming authority. Numeric `player_key`, `full_name`. |
| Pinned naming fixture | `data/fixtures/current/players.json` | Export of `public.players`. Never hand-edited for identity fields. |
| Naming manifest pin | `data/fixtures/current/players.naming-manifest.json` | `exported_at`, `source_label`, `row_count`, identity-projection SHA-256. |
| Identity aliases | Supabase `public.player_identity_aliases`, `public.player_identities` (per `docs/architecture-current.md`) | |
| Review rows | `output/reviewed/...` (per pipeline promotion rule §3) | Triage required; never ignored. |
| Supabase normalized source tables | `public.fp_season_projections`, `public.fp_season_latest_norm`, `public.season_actuals_ytd`, `public.games`, `public.player_value_notes` (per `docs/architecture-current.md`) | Normalized, `player_key`-keyed observations. |
| Import stage entry point | `pipelines/import_supabase_references.py` + `_select_latest_bake` (per `docs/pipeline-rules.md` §7a) | Single choke point for selecting the latest bake. |

---

## 3. Layer 3 — Derived / Model

**Purpose:** Hold everything that is **computed** from the normalized layer — consensus, projections, trade values, adjusted values, two-tier calibrations, source reindexing, fixed-pie anchor math, identity verification, lineage. Nothing in this layer is shown to the user; everything here is fed into the serving layer.

### What belongs here

- Consensus values, source per-source combinations.
- Two-tier calibration artifacts (DDF two-tier leg outputs).
- Adjusted-values views (post-reindex, post-translation; live-rendered adjusted curves still flow through here at bake time — see `docs/pipeline-rules.md` §9 for the live-render policy).
- Reference artifacts (`data/reference/`).
- Cross-source agreement, scale agreement, source-fidelity, identity-verification, data-accuracy, chart-input-coverage, index-math, e2e-fidelity, source-value-lineage, espn-input-comparison, espn-raw-values, imputed VORPs, reweighted values.
- Adjustment-inputs asset (the versioned `trade-value-adjustment-inputs-v1` per `docs/pipeline-rules.md` §9).
- Consolidated values table in Supabase (`public.consolidated_values`, the 8-col PK plus `view`).

### Writers

- All pipeline builders under `pipelines/` that produce derived outputs.
- Bake scripts that combine two-tier legs into consensus / indexed / adjusted values.
- The DDF two-tier calibration stage.

### Readers

- **Serving/api** layer (§4) reads derived artifacts (this is the public read path for the frontend).
- **Ops/monitoring** layer (§5) reads derived diagnostics for health panels and gates.
- **Other derived-layer builders** read each other's outputs (e.g. lineage reads comparison sources, but only within the derived layer; cross-cutting reads must respect the layer ordering).

### Dependency direction

```
raw          →  normalized  →  derived
serving      →  derived
ops/monitor  →  derived
```

### Current repo locations

| Artifact | Path | Notes |
|---|---|---|
| Consolidated values | Supabase `public.consolidated_values` (per `fe-read-contract-v1.md` §3.1.1) | 8-col PK plus `view`. Backing table for `api.player_values`. |
| Two-tier calibration legs | `data/ddf-two-tier/ddf-<date>-<source>-<scoring>-<teams>-0p15/` | Per-source calibration outputs; bake-versioned. |
| Adjustment inputs | `data/adjustment-inputs/adjustment-inputs.json` and `data/adjustment-inputs/jeg242-blend-controls-v1.json` | Versioned asset behind the live-render adjusted curve (`docs/pipeline-rules.md` §9). |
| Comparison fixture (active) | `data/fixtures/current/comparison-sources-data.json` | 8 source sections, combos, source validation, fixed-pie metadata (per `docs/architecture-current.md`). |
| Comparison fixture (full) | `data/fixtures/current/sources_data.json` | 11 source sections; larger than the staged subset. |
| Reference artifacts | `data/reference/` | Cross-source comparison baselines. |
| Adjustment-inputs stage-1 | `data/adjustment-inputs/adjustment-inputs-stage1-empty.json` | Pre-stage-2 build of the adjustment asset. |
| Cross-source agreement | `dist/modules/cross-source-agreement.json` | Derived diagnostic. |
| Scale agreement | `dist/modules/scale-agreement.json` | Used by the trade-value curve diagnostic. |
| Source-fidelity | `dist/modules/source-fidelity.json` | |
| Identity verification | `dist/modules/identity-verification.json` | |
| Data-accuracy | `dist/modules/data-accuracy.json` | Drives the ESPN-zeroed staleness card. |
| Chart-input coverage | `dist/modules/chart-input-coverage.json` | |
| Index math | `dist/modules/index-math.json` | |
| E2E fidelity | (output of `build_e2e_fidelity.py`) | |
| Source-value lineage | `dist/modules/source-value-lineage.json` | Top-25 audit tables; covers 8 source legs + 4 adjusted legs (JEG-98). |
| ESPN input comparison | `dist/modules/espn-input-comparison.json` | |
| ESPN raw values | `dist/modules/espn-raw-values.json` | |
| Player trace | `dist/modules/player-trace.json` | |
| Aggregate diagnostics | `dist/modules/aggregate-diagnostics.json` | |
| Imputed VORPs | (output of `build_imputed_vorps.py`) | |
| Reweighted values | (output of `build_reweighted_values.py`) | |
| Imported versioned bakes (pre-derived mirror) | `data/raw/sources/<source>/...` | **AMBIGUOUS — see note below.** |

**AMBIGUOUS:** The imported versioned snapshots under `data/raw/sources/<source>/` are physically co-located with raw scrapes, but once `_select_latest_bake` (per `docs/pipeline-rules.md` §7a) has resolved them they behave as **normalized source observations** — fail-closed matching and content-vintage stamping have already been applied. The directory convention treats them as raw; the post-select identity treats them as normalized. Treat them as **raw-with-applied-provenance**: a downstream reader is forbidden from skipping the normalization step even when the bytes look normalized.

---

## 4. Layer 4 — Serving / API

**Purpose:** Hold the **small, versioned, frontend-facing read surfaces** the chart and the monitor consume. This is the only layer the frontend may read directly.

### What belongs here

- The five semantic surfaces defined in `docs/contract/fe-read-contract-v1.md` (§2 of that document):
  - `api.player_values` — every value the chart renders, with provenance and coverage metadata.
  - `api.players` — canonical identity.
  - `api.player_context` — news and adjustments per player.
  - `api.product_options` — singleton UI knobs (bench-share bounds, default scoring/teams, default lock order).
  - `api.product_snapshot` — singleton active snapshot plus history (per `fe-read-contract-v1.md` §3.5).
- The versioned contract itself (`contract_version`, semver per `fe-read-contract-v1.md` §7).
- The DDL that projects these surfaces from `public.consolidated_values` and other backend sources.

### Writers

- **Supabase** (project `iskiybsimubiujwuchsl`, schema `api`) — projected from `public.*` per `sql/contract/api_v1.sql`.
- **The bake pipeline** via the contract DDL only.

### Readers

- **Frontend only**, and **only through `product-data.js`** (per `fe-read-contract-v1.md` §1.1). Nothing inside `app/trade-value-chart/` reads anything outside `product-data.js`.
- The `modules/dashboard.html` monitor reads the same surfaces (it is a frontend module).
- **Ops/monitoring** layer reads serving artifacts to verify the contract is live and current.

### Dependency direction

```
raw          →  normalized  →  derived  →  serving
frontend     →  serving     (only)
```

**Forbidden reads from the serving layer:** raw. **Forbidden reads from the frontend:** anything but `product-data.js` to the serving layer.

### Current repo locations

| Artifact | Path | Notes |
|---|---|---|
| Contract DDL | `sql/contract/api_v1.sql` | Draft for review (Roman applies via SQL editor + `NOTIFY pgrst, 'reload schema'`). |
| Consolidated-values source | `sql/consolidated_values.sql` | Backing table; serving surfaces project from here. |
| Migrations | `sql/migrations/...` | Schema evolution for `public.*` (the system-of-record side). The serving schema (`api`) evolves via the contract DDL. |
| FE boundary entry point | `app/trade-value-chart/assets/curve-widget.js`, `app/trade-value-chart/assets/comparison-dashboard.js` (per `docs/architecture-current.md`) | Frontend reads only through `product-data.js`. |
| FE page shell | `app/trade-value-chart/index.html` | Renders from serving surfaces. |
| Monitor | `modules/consolidation.html`, `modules/dashboard.html` | Reads from serving surfaces. |
| Dist artifacts (frontend-shipped) | `dist/assets/comparison-sources-data.json`, `dist/assets/curve-widget.{js,css}`, `dist/assets/comparison-dashboard.{js,css}`, `dist/assets/dashboard-integration.css`, `dist/assets/value-model.js`, `dist/assets/player-news.json`, `dist/assets/reference-freshness.json`, `dist/assets/adjustment-inputs.json` | **AMBIGUOUS — see note below.** |

**AMBIGUOUS:** Today the frontend ships via `dist/assets/comparison-sources-data.json` and `dist/assets/player-news.json`, which are **derived-layer artifacts mirrored into the dist tree** rather than the contract surfaces in `api.*`. The target architecture (per `fe-read-contract-v1.md` §1.4) moves the browser's economics to bake time and the data behind `api.player_values` / `api.player_context`. Until that migration lands, the `dist/assets/` JSONs are a transitional serving surface — they are **derived-layer bytes consumed as if they were serving-layer surfaces**. Mark them AMBIGUOUS and resolve via the `fe-read-contract-v1.md` rollout, not via this doc.

---

## 5. Layer 5 — Ops / Monitoring

**Purpose:** Hold pipeline state, freshness signals, run history, failures, and the artifacts that let a human (or a watchdog) tell whether the system is healthy. This layer **reads** every other layer for diagnostics; it **writes** only its own run-state files.

### What belongs here

- Pipeline run status (`output/comparison-chain-status.json`).
- Import health (`output/source-import-health.json`, `dist/modules/source-import-health.json`, per `docs/import-health-schema.md`).
- Data accuracy / staleness (`dist/modules/data-accuracy.json`, `dist/modules/reference-freshness.json`).
- Pipeline checkpoints (`output/pipeline-checkpoints.json`, `dist/modules/pipeline-checkpoints.json`, `dist/modules/github-actions.json`).
- Live-page scrape (`dist/modules/live-page-scrape.json`).
- Chart health probes (JEG-68 starter-markup sanity, JEG-51 ESPN-zeroed staleness, the source-disagreement metrics).
- The deploy gate (`tests/rendered_gate/gate.mjs`) and its provenance (`rendered-gate.json`).
- GitHub Actions workflow state and run history (per `.github/workflows/`).
- Source-vintage check outputs.
- Risk register entries for durable ops issues.

### Writers

- **Ops/monitoring scripts only** (`pipelines/build_pipeline_checkpoints.py`, `pipelines/verify_import_health.py`, `pipelines/build_data_accuracy.py` and equivalents).
- **GitHub Actions** as the publisher of run history.
- **The watchdog** (`docs/watchdog.md`) — reads; never writes import-health files.

### Readers

- Humans (Jeremy, dispatcher, Codex / Claude / Muse review sessions).
- Watchdog / pull watchdog.
- The deploy gate (`tests/rendered_gate/gate.mjs`).
- `make import-health`, `make validate`, `make sync` (each consults ops/monitoring artifacts before proceeding).

### Dependency direction

```
raw          →  normalized  →  derived  →  serving
ops/monitor  →  every layer below (read-only)
ops/monitor  →  ops/monitor  (writes only its own files)
```

Ops/monitoring is **read-everywhere, write-only-here**. No ops artifact is allowed to advance source content vintage, alter a fixture, or be read by the frontend as a data source. The rendered gate consumes ops artifacts as gate signals, not as product data.

### Current repo locations

| Artifact | Path | Notes |
|---|---|---|
| Comparison-chain status | `output/comparison-chain-status.json` | Per-run status. |
| Import health | `output/source-import-health.json`, `dist/modules/source-import-health.json` | Per `docs/import-health-schema.md`. |
| Pipeline checkpoints | `output/pipeline-checkpoints.json`, `dist/modules/pipeline-checkpoints.json` | |
| Data accuracy | `dist/modules/data-accuracy.json` | Drives ESPN-zeroed staleness card. |
| Reference freshness | `dist/assets/reference-freshness.json` | **AMBIGUOUS — see note below.** |
| GitHub Actions status | `dist/modules/github-actions.json` | |
| Live-page scrape | `dist/modules/live-page-scrape.json` | |
| Source vintage check | (output of `.github/workflows/source-vintage-check.yml`) | Drives `rebuild-chain.yml` dispatch. |
| Rebuild chain | `.github/workflows/rebuild-chain.yml` | Orchestrator. |
| Source-sync workflows | `.github/workflows/{espn,cbsros}-supabase-sync.yml`, `fantasycalc-drift.yml`, `player-trace-rebuild.yml`, `source-vintage-check.yml` | Per-source lifecycle. |
| Deploy workflow | `.github/workflows/pages.yml`, `preview.yml`, `live-page-synthetic.yml` | Publish path. |
| Rendered gate | `tests/rendered_gate/gate.mjs`, `rendered-gate.json` | |
| Pipeline rules | `docs/pipeline-rules.md` | Authoritative methodology for ops. |
| Watchdog spec | `docs/watchdog.md` | Pull watchdog (read-only). |
| Risk register | `docs/risk-register.md` | Durable ops issues. |
| Claude log | `docs/claude-log/` | Session-level claims / verified / open (one file per PR/session; `docs/claude-log.md` is the frozen archive). |
| Pipeline input coverage | `dist/modules/chart-input-coverage.json` | (touches derived but is consumed by ops) |

**AMBIGUOUS:** `dist/assets/reference-freshness.json` lives in the dist tree next to the frontend-shipped assets, so it *appears* to be a serving-layer artifact. By intent it is an **ops/monitoring** artifact consumed by the freshness gate; it just happens to be shipped via the dist tree for the frontend monitor's convenience. Mark it AMBIGUOUS: location is dist/assets, layer is ops/monitoring.

---

## 5.1 Full dependency diagram

```
                          ┌──────────────────────────────────────────────┐
                          │                FRONTEND                       │
                          │   app/trade-value-chart/  modules/*.html      │
                          │   reads ONLY via product-data.js              │
                          └────────────────────┬─────────────────────────┘
                                               │ reads
                                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — SERVING / API                  (Supabase api.* schema)         │
│  api.player_values · api.players · api.player_context ·                  │
│  api.product_options · api.product_snapshot                              │
│  contract_version semver; DDL: sql/contract/api_v1.sql                    │
└────────────▲─────────────────────────────────────────────────────────────┘
             │ reads (projected from)
             │
┌────────────┴──────────────────────────────────────────────────────────────┐
│  LAYER 3 — DERIVED / MODEL                                                 │
│  consolidated_values · two-tier legs · adjustment-inputs · reference ·    │
│  cross-source agreement · scale agreement · source-fidelity · lineage ·   │
│  identity-verification · data-accuracy · chart-input-coverage ·          │
│  index-math · e2e-fidelity · espn-input-comparison · espn-raw-values ·    │
│  imputed-vorps · aggregate-diagnostics · reweighted-values · player-trace│
└────────────▲────────────▲────────────────────────────────────────────────┘
             │            │ reads
             │            │
┌────────────┴────┐  ┌────┴───────────────────────────────────────────────┐
│  LAYER 2 —      │  │  LAYER 3 INTERNAL: cross-derived reads happen here  │
│  NORMALIZED /   │  │  ONLY (derived reads derived); never sideways.      │
│  CORE           │  └─────────────────────────────────────────────────────┘
│  players (canonical) · player_key export · players.json (pinned) ·
│  naming-manifest.json · fp_season_* · season_actuals_ytd · games ·
│  player_value_notes · player_identity_aliases · review_rows ·
│  import_supabase_references._select_latest_bake (single choke point)
└────────────▲─────────────────────────────────────────────────────────────┘
             │ reads
             │
┌────────────┴──────────────────────────────────────────────────────────────┐
│  LAYER 1 — RAW / SOURCE                                                    │
│  Supabase scraped-reference tables (versioned bakes) · data/raw/sources/  │
│  data/inputs/{ecr_draft, espn_pies, prediction_markets, projections.csv}  │
│  Note: data/inputs/player_identity_map.json is AMBIGUOUS (§1).            │
└──────────────────────────────────────────────────────────────────────────┘

                  ┌──────────────────────────────────────────────────────┐
                  │  LAYER 5 — OPS / MONITORING  (read-everywhere,       │
                  │  write-only-here)                                     │
                  │  source-import-health · pipeline-checkpoints ·       │
                  │  comparison-chain-status · data-accuracy ·           │
                  │  reference-freshness · github-actions ·              │
                  │  live-page-scrape · chart health probes ·            │
                  │  rendered-gate.json · .github/workflows/ ·           │
                  │  docs/{risk-register,watchdog,pipeline-rules}.md      │
                  │  Note: dist/assets/reference-freshness.json is        │
                  │  AMBIGUOUS (§5).                                      │
                  └──────────────────────────────────────────────────────┘
```

---

## 6. Open questions for Jeremy (UNRESOLVED — carried forward from JEG-341)

These are the Q1–Q8 the JEG-341 review raised. They are **deliberately not resolved** in this document. The target architecture above is consistent with any of the resolutions below; the right answer is Jeremy's call.

- **Q1 — Browser-side adjustment fit.** Does the adjustment curve (per `docs/pipeline-rules.md` §9) continue to render live in the browser from the versioned `trade-value-adjustment-inputs-v1` asset, or does some or all of it move to bake time? `fe-read-contract-v1.md` §1.4 already moves the **two-tier calibration** to bake time and keeps the **bench-share slider** as a browser `vector+blend`. Adjustment fit is a separate decision (parametric vs static, per-combo vs per-position vs global, and whether the browser still solves anything).
- **Q2 — "Vegas" definition.** The market side is named **"Vegas"** in user-facing copy (pipeline-rules §6). What is "Vegas" as a data source for this product? Today the leg is `data/inputs/prediction_markets_season.csv` (raw layer 1). Does the leg stay raw-only, get normalized into a Vegas section in the comparison fixture, or stay out of the dashboard entirely? Per pipeline-rules §7, Vegas/prediction-markets is "never imported as a comparison source", which rules it out of layer-4 surfaces for the chart but does not yet say what layer it lives in beyond raw.
- **Q3 — Fixed-pie anchor.** Which source's pie is the anchor for fixed-pie reindexing, and is it still ESPN, or has the reindex anchor moved? `docs/pipeline-rules.md` §3 says "The reindex anchor is the fixture's ESPN leg -- NOT the retired Monday rail the existing fixture sections were baked against." Today's `comparison-sources-data.json` carries the eight published legs with reindexed metadata; the anchor decision is still an open call.
- **Q4 — Tier-2 scope.** What sources get the two-tier calibration treatment, and at what combo granularity? `data/ddf-two-tier/` today has ESPN, CBS ROS, and Razzball legs across (3 scoring × 4 teams = 12 combos) — FantasyCalc and the as-published sources do not run two-tier. Is Tier-2 permanently ESPN / CBS ROS / Razzball only, or does Tier-2 expand?
- **Q5 — VORP glossary. RESOLVED 2026-10-06 (copy-vorp-001): the user-facing term is "VORP vs waivers".** Original question: user-facing copy uses **"value above waivers"** (pipeline-rules §6). The internal data key `espn_vorp` is exempt from that rule (and a test enforces it). Is "value above waivers" the final user-facing term, or does it get a richer glossary / footer copy that the JEG-341 review's audience wants? `espn_vorp` as an internal key stays.
- **Q6 — JEG-322 family scope.** The JEG-329/332/333/334 family of on-demand VORP views is parked per `fe-read-contract-v1.md` §1.2 ("JEG-329/332/333/334 are parked (JEG-331 verdict: the precondition failed)"). Does the family stay parked, get a defined v2 extension point, or get killed outright? The contract reserves `view='vorp_on_demand'` as a future extension if Jeremy approves. **Resolved 2026-10-06 (`docs/decisions.md` league-settings-001): the on-demand Postgres family is retired; one canonical setup (12 teams, standard roster) is saved per scoring format and every other league setting is derived in the browser.**
- **Q7 — Supabase system-of-record scope.** Which tables are **system of record** in Supabase vs derived-and-pinned into the repo? Today the canonical `players` table is the naming authority (pipeline-rules §1) and scraped references are stored in Supabase (pipeline-rules §7). Does the system-of-record scope extend to `consolidated_values`, `source_trade_values`, the two-tier calibration outputs, or the adjustment-inputs asset? This affects whether layer-3 derived tables live in Supabase or only in repo paths.
- **Q8 — Carried from JEG-341 review: ambiguity around `dist/assets/*.json` serving shape.** Until the `fe-read-contract-v1.md` rollout lands, `dist/assets/comparison-sources-data.json` and `dist/assets/player-news.json` are derived-layer bytes consumed as serving surfaces. Does that dual role get codified as a transitional pattern, or does the migration timeline get accelerated?

---

## 7. Hard-constraint self-check (re-read against the brief)

- **No methodology changes.** Methodology contracts in `docs/pipeline-rules.md` are referenced but not edited. Naming authority, null-not-zero, content-vintage-not-pull-time, fail-closed matching, versioned bakes — all preserved as-is. This document describes where things live, not what they compute.
- **No new user-facing copy claims.** The only approved terms referenced are **Data Driven Football**, **DDF methodology**, **Vegas**, and **value above waivers**. No marketing language was invented.
- **All Q1–Q8 carried as open questions.** §6 lists Q1 through Q8 verbatim from the brief, none of them resolved.
- **No other source files edited.** `docs/architecture-target.md` is the only new doc; the rest of the repo is untouched by this completion.

---

## 8. Companion report

A short delivery report accompanies this document at `lanes/inbox/minimax/JEG-341-A.md` (per the ticket's deliverable list).