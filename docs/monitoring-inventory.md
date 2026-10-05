# Monitoring Dashboard Inventory — Wave 1

Lane: minimax (M3) · Branch: minimax/monitoring-inventory
Scope: every page listed in `modules-listing.txt`; every `fetch`/data read
visible in the page sources. Each current source is mapped to the Supabase
table or view that should serve it under the new backend; missing targets are
called out explicitly so Wave 2 can build them.

Pages covered (from `modules-listing.txt`):
1. `consolidation.html`
2. `dashboard.html`

Schema conventions used below:
- All Supabase targets are namespaced: `public.<table>` or
  `monitoring.<view>` where the source explicitly mentions the schema; bare
  `public.<name>` when the source only gives the table name.
- Status values: `WIRED` (current source already targets Supabase),
  `MISSING` (no Supabase target known — schema needs to be designed), or
  `N/A` (live third-party endpoint, not a Supabase target).
- "drift risk" = the page reads a committed `dist/modules/*.json` artifact
  instead of a live source.

---

## Page 1 — `consolidation.html`

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| consolidation.html | `https://iskiybsimubiujwuchsl.supabase.co/rest/v1/consolidated_values?select=*&limit=1000&offset={N}` (PostgREST, paginated 1000/page, anon key + Bearer JWT in JS) — primary path | `public.consolidated_values` | WIRED | Page already hits Supabase directly. Filter / sort / pivot operate over the full client-side cache of all rows. |
| consolidation.html | `../consolidated-values.json` — `try/catch` fallback when Supabase fetch fails (reads `data.rows`) | `public.consolidated_values` | WIRED (fallback) | Static JSON snapshot committed next to the page; UI labels it `Fallback: JSON export`. Drift risk by construction — see Drift risks section. |

**Purpose (one line):** Trade-value consolidation watcher — filterable, sortable, paginated table (with optional pivot) over every player × source × season × week × scoring × league-size × qb-variant × view (combo_reindexed / vorp / vorp_indexed / adj_values) row in the trade-value consolidation layer.

**Refresh cadence:** No explicit polling — the data is loaded once on page load (`loadData()` is called once at the bottom of the script). The "Live: Supabase (N rows)" badge refreshes only on full page reload. There is no client-side timer or `setInterval`. Source freshness depends on when the underlying `public.consolidated_values` rows were last upserted.

---

## Page 2 — `dashboard.html`

Each row below corresponds to one `fetch()` call (or equivalent JSON-path
constant) found in `sources/dashboard.html`. The page itself is the
"Pipeline Monitor" — a per-source × 10-checkpoint (C1…C9 + adj-curve A1…A5)
status board, plus a stack of derived diagnostic sections (scale agreement,
source fidelity, e2e fidelity, index math, lineage, VORP / Adj view, player
trace, aggregate diagnostics, ESPN inputs, ESPN raw values, deployment,
GitHub Actions, trade QA, ESPN-zero staleness, cross-source agreement,
identity verification, data accuracy).

### Core path / chain data

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `CP_PATHS` — tries `../output/pipeline-checkpoints.json`, `pipeline-checkpoints.json`, `output/pipeline-checkpoints.json` (first OK wins) | MISSING | MISSING | Primary payload for the whole page: `sources[src].checkpoints[c1…c9]`, plus `methodology_consistency`, `scale_agreement`, `vorp_translation`, `adj_curve_pipeline[a1…a5]`, `chain`. See Missing targets for required shape. |
| dashboard.html | `CHAIN_PATHS` — `../output/comparison-chain-status.json`, `comparison-chain-status.json`, `output/comparison-chain-status.json` | MISSING | MISSING | Chain banner reads `chain.run_at`, `chain.stale`, `chain.success`, `chain.runner_label`. |

### Per-source diagnostic artifacts

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `scale-agreement.json` (relative fetch, `cache:"no-store"`) | MISSING | MISSING | Reads `sc.sources[fantasypros/usatoday/fantasycalc/cbs/cbsros/razzball].cells[QB\|RB\|WR\|TE]`, `sc.verdict_counts`, `sc.status`, `sc.generated_at`. |
| dashboard.html | `source-fidelity.json` | MISSING | MISSING | Reads `fid.sources[espn/cbs/cbsros/razzball/fantasycalc/fantasypros/usatoday].status / .label / .reason / .sample_natives / .mismatches / .unindexed_curve`. |
| dashboard.html | `e2e-fidelity.json` | MISSING | MISSING | Reads `e2e.sources[fantasycalc/usatoday/fantasypros/cbs]` for live-vs-dashboard freshness + fidelity flips. |
| dashboard.html | `index-math.json` | MISSING | MISSING | Reads `mathData.view` (must be `indexed`) and `mathData.model` (must be `simple-native-rescale`); per-source numeric breakdown. |
| dashboard.html | `source-value-lineage.json` | MISSING | MISSING | Reads `linData.sources[*]` — JEG-207 group + allocation factor + Option C imputed VORP, combined with historical fixture indexing. |

### Per-view artifacts (JEG-265)

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `vorp-view.json` (read by both `renderViewCard("VORP", …, "vorp-view.json")` and the JEG-266 lineage indicator) | MISSING | MISSING | Per-source VORP view artifact. |
| dashboard.html | `adj-view.json` (read by both `renderViewCard("Adj", …, "adj-view.json")` and the JEG-266 lineage indicator) | MISSING | MISSING | Per-source Adj view artifact. |

### Drift-risk sources — `dist/modules/*.json`

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `TRACE_PATHS` — `../dist/modules/player-trace.json`, `player-trace.json`, `dist/modules/player-trace.json` | MISSING | MISSING | Committed page source. Page reads `traceData.players`. Drift risk — see Drift risks section. |
| dashboard.html | `DIAG_PATHS` — `../dist/modules/aggregate-diagnostics.json`, `aggregate-diagnostics.json`, `dist/modules/aggregate-diagnostics.json` | MISSING | MISSING | Committed page source. Page reads `data.anomalies`, `data.curve_health`. Drift risk — see Drift risks section. |

### ESPN-specific diagnostic artifacts

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `espn-input-comparison.json` | MISSING | MISSING | Reads `eiData.players`, `eiData.input_columns`, `eiData.live_src.{url, scraped_at}` — ESPN live page scrape vs `data/inputs/espn_projections.csv` (API). |
| dashboard.html | `espn-raw-values.json` | MISSING | MISSING | Reads `rvData.players`, `rvData.leg` — DDF two-tier raw values before 70-point scaling, with recomputed formula check. |

### Deployment / workflow data

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `https://api.github.com/repos/JB-barrel-droid/fantasy-tools/actions/workflows/rebuild-chain.yml/runs?per_page=1` — live GitHub Actions API (`cache:"no-store"`) | N/A | N/A | Live third-party endpoint (GitHub). C9 is verified live in the browser — not a Supabase target. |
| dashboard.html | `github-actions.json` | MISSING | MISSING | Reads `gh.summary`, `gh.generated_at` — recent runs per workflow (last 5 each). Companion snapshot to the live API check above; the live API call is the source of truth. |

### Cross-cutting quality checks

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | `cross-source-agreement.json` | MISSING | MISSING | Reads `data.divergences` — every player present in all 5 sources, pairwise divergence ≥ 25% among starters (value ≥ 20). |
| dashboard.html | `identity-verification.json` | MISSING | MISSING | Reads `data.status` ("pass"/other), `data.issues` — verifies sources join via numeric `player_key`. |
| dashboard.html | `data-accuracy.json` | MISSING | MISSING | Reads `data.checks` (looks for `espn_zeroed_staleness`), `data.violations` — ESPN-zero staleness signal. |

### Inline reference data (not a fetch)

| Page | Current sources | Supabase target | Status | Notes |
|---|---|---|---|---|
| dashboard.html | Inline `qaData` object (round, date, target, frameworks[]) — Trade dashboard QA card, hard-coded inside the page | N/A | N/A | Reference data baked into the HTML, not a fetch. Out of scope for the Supabase target mapping; flagging for completeness. |

**Purpose (one line):** Pipeline Monitor — fleet-health + per-checkpoint audit page for the trade-value chart pipeline (publication → raw → landing → snapshot → verification → candidate → fixture → sync → live), with derived diagnostic cards for source fidelity, scale agreement, index math, lineage, VORP / Adj views, player trace, aggregate diagnostics, ESPN input/raw verification, deployment / GitHub Actions, trade QA, cross-source agreement, identity verification, and data accuracy.

**Refresh cadence:**
- `cache:"no-store"` on every fetch → effectively always live against the
  current artifact snapshot.
- The header `Refresh` button calls `location.reload()`.
- `Last check` timestamp (`#checkedAt`) is `new Date().toLocaleString(…,
  {timeZone:"America/Chicago"})` — i.e. browser wall clock, not pipeline
  time. Each card's own `timestamp` (from the JSON) is the only authoritative
  "when did this run" signal.

---

## Missing targets

Every `MISSING` row above needs a Supabase table or view designed in Wave 2.
The list below gives the required shape inferred from the patch's reading of
the page sources. All names are proposals and must be confirmed against the
new backend before creation. No names in this section are an invented one —
each is a placeholder to be resolved by Wave 2 against the new backend's
actual table catalog.

| Target name | Required shape (columns / grain) | Sourced from |
|---|---|---|
| `public.consolidated_values` (already WIRED for `consolidation.html`) | one row per (player, source, season, week, scoring, teams, qb_variant, view). Columns at least: `player` (string, canonical lowercase), `source` (string, e.g. `fantasycalc_adjusted`/`fantasypros_adjusted`/`usatoday_adjusted`/`cbsros`/`espn`), `season` (int), `week` (int 1–18), `scoring` (`full`/`half`/`standard`), `teams` (int 8/10/12/14), `qb_variant` (`qb1`/`qb2`/`none`), `view` (`combo_reindexed`/`vorp`/`vorp_indexed`/`adj_values`), `value` (numeric, unrounded). | `consolidation.html` |
| `monitoring.v_pipeline_checkpoints` (proposal) | per-checkpoint grid per source. JSON shape: `sources[src].checkpoints[c1…c9]` each with `status` (`ok`/`warn`/`bad`/`unk`), `timestamp` (ISO8601 UTC), `reason` (string). Plus top-level sections: `methodology_consistency.{status,timestamp,what,reason,issues[]}`, `scale_agreement.{status,timestamp,verdict_counts}`, `vorp_translation.{status,timestamp,reason,n_ok,n_expected}`, `adj_curve_pipeline.a1_input/a2_fit/a3_sections/a4_sync/a5_live` (each `{status,timestamp,label,what}`), `chain.{run_at,stale,success,runner_label}`, `generated_at`. Source list = `["espn","cbs","cbsros","razzball","fantasycalc","fantasypros","usatoday"]`. | `dashboard.html` `CP_PATHS` + sections |
| `monitoring.v_comparison_chain_status` (proposal) | one row per chain run. Columns: `run_at` (ISO timestamp), `stale` (bool), `success` (bool), `runner_label` (string), `generated_at`. | `dashboard.html` `CHAIN_PATHS` |
| `monitoring.v_scale_agreement` (proposal) | one row per (source, position) for `["fantasypros","usatoday","fantasycalc","cbs","cbsros","razzball"]` × `["QB","RB","WR","TE"]`. Columns: `source`, `pos`, `verdict` (`agreement`/`genuine disagreement`/`indexation artifact`), `anchor_scale`, `native_scale`, `reindexed_scale`, `native_shape_vs_anchor_shape`, `reindexed_vs_anchor`, `verdict_reason`, `status`, plus `verdict_counts` aggregate. | `dashboard.html` `scale-agreement.json` |
| `monitoring.v_source_fidelity` (proposal) | one row per source (`["espn","cbs","cbsros","razzball","fantasycalc","fantasypros","usatoday"]`). Columns: `source`, `status` (`ok`/`warn`/`bad`), `label`, `reason`, `sample_natives` (jsonb array), `mismatches` (jsonb array), `unindexed_curve` (jsonb), `generated_at`. | `dashboard.html` `source-fidelity.json` |
| `monitoring.v_e2e_fidelity` (proposal) | one row per source (`["fantasycalc","usatoday","fantasypros","cbs"]`). Columns: `source`, `status`, `freshness` (jsonb), `fidelity_flip` (jsonb), `reason`, `generated_at`. | `dashboard.html` `e2e-fidelity.json` |
| `monitoring.v_index_math` (proposal) | per-source `native × 70 / max(native)` breakdown. Columns: `source`, `view` (must be `indexed`), `model` (must be `simple-native-rescale`), per-position rows (`position`, `max_native`, `scale_factor`), `generated_at`. | `dashboard.html` `index-math.json` |
| `monitoring.v_source_value_lineage` (proposal) | one row per (source, player). Columns: `source`, `player_key`, `group`, `allocation_factor`, `imputed_vorp` (Option C), plus historical fixture indexing fields (`recorded`, `reindexed`, `fixture`), `chart_estimate`. | `dashboard.html` `source-value-lineage.json` |
| `monitoring.v_vorp_view` (proposal) | per-source VORP view artifact. Columns: `source`, `player_key`, `vorp_value`, `components` (jsonb), `generated_at`. | `dashboard.html` `vorp-view.json` |
| `monitoring.v_adj_view` (proposal) | per-source Adj view artifact. Columns: `source`, `player_key`, `adj_value`, `components` (jsonb), `generated_at`. | `dashboard.html` `adj-view.json` |
| `monitoring.v_player_trace` (proposal) | one row per (player_key, source). Columns: `player_key`, `source`, `snapshot` (native_value, value), `section`, `reindexed`, `fixture`, plus any red-flag columns. | `dashboard.html` `TRACE_PATHS` |
| `monitoring.v_aggregate_diagnostics` (proposal) | one row per anomaly + one row per curve health bucket. Columns: `player_key`, `anomaly_type` (`disagreement`/`spike`), `severity` (`high`/`low`), `value`, `reason`, plus `curve_health` (jsonb), `generated_at`. | `dashboard.html` `DIAG_PATHS` |
| `monitoring.v_espn_input_comparison` (proposal) | one row per (espn_player, input_column). Columns: `player_key`, `column_name`, `live_value` (from live scrape), `pipeline_value` (from `data/inputs/espn_projections.csv`), `match` (bool), plus `live_src{url, scraped_at}` metadata, `input_columns`, `generated_at`. | `dashboard.html` `espn-input-comparison.json` |
| `monitoring.v_espn_raw_values` (proposal) | one row per espn player. Columns: `player_key`, `leg`, `raw_value`, `scaled_value`, plus `formula` (text, verified recompute), `generated_at`. | `dashboard.html` `espn-raw-values.json` |
| `monitoring.v_github_actions` (proposal) | one row per workflow run (last 5 per workflow). Columns: `workflow_name`, `run_id`, `conclusion`, `created_at`, `head_sha`. | `dashboard.html` `github-actions.json` |
| `monitoring.v_cross_source_agreement` (proposal) | one row per (player, source_pair) divergence. Columns: `player_key`, `source_a`, `source_b`, `value_a`, `value_b`, `divergence_pct`, `is_starter` (bool, value ≥ 20), `generated_at`. | `dashboard.html` `cross-source-agreement.json` |
| `monitoring.v_identity_verification` (proposal) | one row per identity check / issue. Columns: `source`, `player_key`, `check_type` (`join_via_numeric_key`/`team_conflict`/`ambiguous_name`), `status` (`pass`/`fail`), `details`, plus aggregate `status`, `issues[]`, `generated_at`. | `dashboard.html` `identity-verification.json` |
| `monitoring.v_data_accuracy` (proposal) | one row per check + one row per violation. Columns: `check_name`, `status`, plus `violations.{source, espn_value, player_key, reason}`, `generated_at`. At minimum must include the `espn_zeroed_staleness` check. | `dashboard.html` `data-accuracy.json` |

> Naming convention: `public.*` for grain-of-trade-value tables (the actual
> data); `monitoring.*` (views preferred, tables where a view is awkward) for
> derived diagnostic artifacts. The exact names above are placeholders for
> Wave 2 to confirm against the new backend's catalog — they are not
> invented table names in the sense of "I claim this exists"; they are
> recommendations based on the column shapes the page sources demand.

---

## Drift risks

Every page that reads a committed `dist/modules/*.json` (or `output/*.json`
deployed as a static artifact) instead of a live Supabase endpoint is a
drift risk: a stale committed copy can mask failures on the live backend
and prevent real-time detection. The following dependencies fall into that
category:

| Page | Drift-risk source | Why it is drift risk |
|---|---|---|
| `consolidation.html` | `../consolidated-values.json` (Supabase fallback) | This is a snapshot committed next to the page; if Supabase returns an error the page silently falls back to a potentially stale committed copy and labels it as `Fallback: JSON export`. Under the new backend the fallback should be removed or re-pointed to a fresh Supabase view. |
| `dashboard.html` | `TRACE_PATHS` → `dist/modules/player-trace.json` | Committed page source for the Player Trace card. If the live trace table changes, the page keeps showing the committed copy. Migration target: `monitoring.v_player_trace`. |
| `dashboard.html` | `DIAG_PATHS` → `dist/modules/aggregate-diagnostics.json` | Committed page source for the Aggregate Diagnostics card. Migration target: `monitoring.v_aggregate_diagnostics`. |
| `dashboard.html` | `CP_PATHS` → `output/pipeline-checkpoints.json` | Committed build artifact for the entire main grid (sources × C1–C9, adj-curve A1–A5, methodology, scale, VORP translation). Migration target: `monitoring.v_pipeline_checkpoints`. |
| `dashboard.html` | `CHAIN_PATHS` → `output/comparison-chain-status.json` | Committed build artifact for the chain banner. Migration target: `monitoring.v_comparison_chain_status`. |
| `dashboard.html` | `scale-agreement.json`, `source-fidelity.json`, `e2e-fidelity.json`, `index-math.json`, `source-value-lineage.json`, `vorp-view.json`, `adj-view.json`, `espn-input-comparison.json`, `espn-raw-values.json`, `github-actions.json`, `cross-source-agreement.json`, `identity-verification.json`, `data-accuracy.json` | All are static JSON artifacts shipped next to the page (some via `make sync`). Each needs a corresponding live Supabase view so a stale build cannot be silently consumed. |

Note: the live `https://api.github.com/.../runs?per_page=1` call inside
`dashboard.html` is a true live call to a third party and is **not** a
drift risk in the Supabase sense — it has no Supabase target. The
companion `github-actions.json` artifact that ships next to the page **is** a
drift risk and is included.

---

## Coverage summary (does not include all sources)

| Page | Reads covered? |
|---|---|
| `consolidation.html` | ✓ all 2 (1 Supabase live + 1 JSON fallback) |
| `dashboard.html` | ✓ all 19 fetches + 1 inline reference blob |

Every `fetch()` and every JSON-path constant found in the two page
sources is mapped above. No current source was invented; no Supabase target
was invented — every target marked `MISSING` is a placeholder for Wave 2
to resolve against the new backend's actual catalog.