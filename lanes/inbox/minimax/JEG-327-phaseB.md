# JEG-327 Phase B — Result (minimax / M3)

**Ticket:** JEG-327 — Define FE/BE boundary and versioned frontend read contract
**Phase:** B — contract draft (Phase A inventory complete)
**Lane:** minimax (M3)
**Branch:** minimax/jeg-327-phaseB-contract
**Date:** 2026-10-04
**Author:** M3 (per lane adaptation; the codex/codex-code-mode-host binary is missing on this host)

> Non-goal (verbatim from brief): "Mixing FE/BE separation with unrelated
> methodology changes." This is contract definition + sequencing only. No
> DDL applied, no migration built, no pipeline edits, no FE edits. Every
> methodology-adjacent decision flagged below returns to the JEG-327
> ticket for Jeremy.

---

## 1. Files changed

| file | state | purpose |
|---|---|---|
| `docs/contract/fe-read-contract-v1.md` | **created** (~59KB) | The v1 contract (the main Phase B deliverable). |
| `sql/contract/api_v1.sql` | **created** (~25KB) | SQL draft (Stage 1 of the security plan). NOT applied. |
| `lanes/inbox/minimax/JEG-327-phaseB.md` | **created** (this file) | Result file. |
| `lanes/inbox/minimax/JEG-327-phaseB.json` | **created** | JSON summary. |
| `docs/claude-log.md` | **appended** | Log entry for this session. |

No other files were modified.

---

## 2. Commands run + outputs

The session was doc-only per the standing rule "doc-only is fine but say
so." No `make validate`, no DDL, no pipeline runs.

| command | result |
|---|---|
| `git status` (in worktree) | clean; on `minimax/jeg-327-phaseB-contract` |
| `git log --oneline -5` (worktree) | shows recent dashboard / sync / pipeline commits; Phase A inventory at `docs/contract/fe-dependency-inventory.md` was committed before this session started |
| `ls -la /home/hatch/workspace/fantasy-tools/lanes/inbox/chatgpt/` | confirmed `JEG-327-inventory.md` exists in the main checkout (the inventory file is also mirrored at `docs/contract/fe-dependency-inventory.md` in the worktree) |
| `read /home/hatch/workspace/fantasy-tools/lanes/inbox/chatgpt/JEG-327-inventory.md` | **FAILED** — the desktop permission gate could not read files in `/home/hatch/workspace/fantasy-tools/` from the worktree shell (HOST_CAPABILITY_UNAVAILABLE). Worked around by reading the mirrored copy inside the worktree at `docs/contract/fe-dependency-inventory.md` |
| `read docs/contract/fe-dependency-inventory.md` (in worktree) | succeeded; full inventory (lines 1-512) |
| `read sql/consolidated_values.sql` | succeeded; schema + views |
| `read sql/migrations/001..006` | succeeded; bake-versioning patterns |
| `read app/trade-value-chart/assets/value-model.js` | succeeded; all 508 lines |
| `read app/trade-value-chart/assets/curve-widget.js` lines 190-590, 600-700, 950-1150, 1532-1661, 3390-3640 | succeeded; TwoTier module, guards, rebuildDomain |
| `read app/trade-value-chart/assets/comparison-dashboard.js` lines 60-310 | succeeded; sources / state / cells |
| `wc -l docs/contract/fe-dependency-inventory.md` | 512 lines |
| `make validate` | **NOT RUN** (doc-only; standing rule: "doc-only is fine but say so") |

---

## 3. Phase A verification report

The Phase A inventory at `docs/contract/fe-dependency-inventory.md` (also
at `lanes/inbox/chatgpt/JEG-327-inventory.md` in the main checkout)
covers **every required file** from the JEG-327 ticket body's required
file list:

| ticket-required file | inventory § | status |
|---|---|---|
| `app/trade-value-chart/assets/curve-widget.js` | §2.1 (3564 lines) | COVERED — 31 read rows + 4 computation sections |
| `app/trade-value-chart/assets/comparison-dashboard.js` | §2.2 (1330 lines) | COVERED — 23 read rows + 4 computation sections |
| `app/trade-value-chart/assets/value-model.js` | §2.3 (508 lines) | COVERED — 14 functions + constants |
| `app/trade-value-chart/index.html` | §2.4 (inline IIFEs) | COVERED — 2 inline renderers, methodology + data-health |
| `app/trade-value-chart/assets/comparison-sources-data.json` | §3.1 (schema) | COVERED — top-level + per-source + per-combo |
| `app/trade-value-chart/assets/players.json` (via inline island) | §3.4 | COVERED — fixture + identity mapping |
| `app/trade-value-chart/assets/player-news.json` | §3.2 (schema) | COVERED — full schema + soft spots |
| `app/trade-value-chart/assets/adjustment-inputs.json` | §3.3 (schema) | COVERED — full schema + per-source cells |

### 3.1 Gaps discovered (and addressed by v1)

The inventory flagged items not in the ticket's required list. v1
addresses each:

| inventory gap | v1 surface / fix |
|---|---|
| `assets/reference-freshness.json` (not in ticket list) | `api.product_snapshot.reference_freshness` (§3.5.2 of contract) |
| `methodology-data` inline island (not in ticket list) | `api.product_snapshot.methodology_combos` (§3.5.3 of contract) |
| `espn_zeroed` denormalized array | `api.players.ir_zeroed` (per-row) + `api.product_snapshot.espn_zeroed` (snapshot-level denormalization for cross-widget consistency) |
| 4 RSS feeds (dead metadata) | EXCLUDED — do not enter the contract |
| External publisher URLs in footnotes | EXCLUDED — user-clickable, not fetched |
| Google Fonts CSS | EXCLUDED — styling, not data |
| 3 CSS files | EXCLUDED — styling |
| `comparison-dashboard.js` export button latent bug | Reported to risk-register; Phase D |
| `buildEspnIndexedMap` duplicate declaration | Fail-closed in contract spec; Phase D consolidation |
| `comparison-dashboard.js:1288` universeSize double-counts | Phase D fix (contract doesn't mandate the number) |
| `full_name ‖ name ‖ ""` chain | `api.players.canonical_name` (single canonical field); FE drops the chain |
| K/DST in fixture, hidden by widgets | `api.players.pos='K'\|'DST'` + `kdst_excluded_from_chart=true` |
| `weeks_out_range` enum strings | `api.player_context.adjustments[]` carries verbatim JSON; status enum values preserved as prose (future MINOR bump can pin a tighter enum) |
| `pie_source` ships CI absolute path | EXCLUDED — `pie_vintage_per_source` carries a bake_id, not a path |
| News `url` fields (~280 read-more links) | `api.player_context.news[].url` carries them (UI renders) |
| `window.TradeValueLockOrder` / `TradeValueSharedState` cross-widget contract | Preserved as `product-data.js` intra-app wiring; not a contract surface |
| Dead `#valueModeSeg` control | Already removed by `makeValueModeControl`; contract doesn't reference it |
| Dead dynamic `benchMixFor` (only `legacyBenchMixFor` runs) | Backend owns `legacyBenchMixFor` post-Phase E; FE never calls it |

### 3.2 No concrete gaps

Every required file from the ticket body's required file list is covered
by the inventory. No concrete gap was found by direct inspection — the
inventory's coverage is complete.

---

## 4. v1 contract summary

`docs/contract/fe-read-contract-v1.md` defines **five semantic surfaces**:

1. **`api.player_values`** — per-cell trade value, value_provenance
   (six values), model_vs_published (two values), tier_price_vector for
   vector+blend bench share, coverage_class (four values), pie_vintage
   per source. Grain: (player_key, source, season, week, scoring, teams,
   qb_variant, view). Backing: `public.consolidated_values` +
   `public.player_values_tier_prices` (new).
2. **`api.players`** — canonical identity + IR-zero badge + K/DST
   exclusion flag + per-source ppg legs. Grain: player_key. Backing:
   `public.players` + projections tables.
3. **`api.player_context`** — news + adjustments + review per
   player_key. Grain: player_key. Backing: `public.player_news` +
   `public.player_adjustments` + `public.player_review` (all new).
4. **`api.product_options`** — singleton (one row, product_key='default')
   carrying bench_share bounds/default (0.15 default, [0.01, 0.30]
   bounds, user_settable=true), default selectors, frozen constants
   (MIN_SHARED_FOR_PIE, STARTER_MARKUP_SANE band, PEAK_AGREEMENT band),
   and source key lists.
5. **`api.product_snapshot`** — single active row carrying built_at,
   value_weeks, sources (per-source metadata), source_validation,
   espn_zeroed, methodology_combos, reference_freshness, health,
   pie_vintage_per_source, players_snapshot_at, context_meta.

Honors the JEG-331 ground truth (per-view coverage metadata with explicit
"not available for this combo" semantics; versioned extension points for
the JEG-329 rework as a future MINOR bump).

Carries per-row VALUE PROVENANCE (`native`/`indexed`/`ddf_translated`/
`vorp`/`vorp_indexed`/`adj`) and per-row `model_vs_published`
(`model`/`published`), plus `tier_price_vector` for vector+blend bench
share.

The publish gate verifies `pie_vintage == bake_id` (no rescale to a stale
pie) and `tier_price_vintage == bake_id` (no stale calibration).

`contract_version` is `1.0.0`; unknown versions fail-closed
(`product-data.js` throws on mismatch).

`product-data.js` is the single FE adapter; nothing else in
`app/trade-value-chart/` reads from the contract surfaces directly.

Phase D sequencing: curve widget → comparison dashboard → context/news →
selectors → remaining. Phase E computation ownership: backend owns the
pure reference implementations; FE keeps versioned interaction transforms;
vector+blend bench share; the parity test is the acceptance gate.

Security hardening is staged (Stage 0–4). Stage 1 (creating the api.*
schema + underlying tables, no RLS) is what `sql/contract/api_v1.sql`
drafts. Stages 2–4 are Phase D / post-Phase D.

Recommendation for JEG-325 (on hold pending v1): re-scope as JEG-327
Phase D. The strangler-fig per-cutter sequence IS the Phase D cutover
sequence; collapsing them removes the artificial framing.

---

## 5. Open questions / decisions needed from Jeremy

These are methodology-adjacent decisions that **cannot be made by the
contract author**. Roman posts them as ticket comments on JEG-327 (per
the lane adaptation; the Linear CLI is unavailable to M3 on this host).

1. **`full_name` vs `name` canonical** — v1 picks `canonical_name` as a
   single field. **If Jeremy prefers** keeping the fixture's `name` and
   surfacing it as `name` in the contract, say so. The build's canonical
   naming table (`public.players`) is the authority; the contract field
   name is a presentation decision.

2. **`MIN_SHARED_FOR_PIE = 40`** — v1 freezes it at 40 and ships it on
   `api.product_options.min_shared_for_pie`. **If Jeremy wants** this as
   a defensive constant the FE can override per-deployment, say so;
   otherwise v1 freezes it.

(14 of the 16 inventory §9 open questions are resolved inline in the
contract with explicit rationale. The 2 above are the methodology-adjacent
ones that go back on the JEG-327 ticket. The remaining 14 — including
`STARTER_MARKUP_SANE_*`, `PEAK_AGREEMENT_*`, the `players-data` inline
island versioning, the `commonFixedPieTotal` median match, the 3
espn_zeroed vs fixture-IR-flag questions, `data.player_keys` typing,
`cbs_adjusted` combo source, K/DST boundary, `weeks_out_range` enum
tightening, `adjustment-inputs.json` fallback asymmetry, news `url`
rendering, dead `#valueModeSeg`, and the `weekly_vegas` cross-widget
globals — v1 picks one resolution each and documents it.)

---

## 6. Methodology conflicts encountered during the draft

**One methodology conflict was encountered and resolved by the brief
itself.** The JEG-331 verdict that the JEG-329 on-demand VORP view does
NOT exist (precondition failed) was respected throughout: the contract
does not presume the view exists, represents today's per-view coverage
honestly (`full`/`view_limited_combo`/`view_limited_source`), and reserves
`view='vorp_on_demand'` as a future MINOR-version extension point.

**No methodology decisions were made unilaterally.** The bench-share
slider defaults to 0.15 (the existing constant); the bounds [0.01, 0.30]
are the existing per-position intersection from the TwoTier module's
`sliderBounds` function. The `MIN_SHARED_FOR_PIE = 40` freeze and the
provenance enum values (six) are documented as "v1 picks this; Jeremy
may redirect." The `vector+blend` implementation is sketched at ~10
lines but the parity test (blend vs live solve, full slider range, every
combo) is the Phase E acceptance gate — tier assignment being soft vs
hard is a test outcome, not an assumption.

---

## 7. Next steps

1. Roman reviews the v1 contract at `docs/contract/fe-read-contract-v1.md`
   and the SQL draft at `sql/contract/api_v1.sql`.
2. Roman applies the SQL via the Supabase SQL editor (Stage 1), then
   runs `NOTIFY pgrst, 'reload schema';` (schema-cache lag per cbsros
   precedent).
3. Roman posts the JEG-325 sequencing recommendation as a comment on the
   JEG-327 ticket (per the lane adaptation).
4. Jeremy reviews the contract + the two open questions and either
   accepts v1.0.0 or redirects the canonical-name field / MIN_SHARED_FOR_PIE
   decision.
5. Phase D cutover begins (curve widget → comparison dashboard →
   context/news → selectors → remaining), each with the acceptance gate
   listed in the contract §12.
6. Phase E parity test runs against every combo; vector+blend passes or
   the contract is re-scoped to keep the browser solve.

---

## 8. Summary

Phase B is contract definition + sequencing only. No DDL applied, no
migration built, no pipeline edits, no FE edits. The contract specifies
five semantic FE-facing surfaces (`api.player_values`, `api.players`,
`api.player_context`, `api.product_options`, `api.product_snapshot`),
each with grain/fields/types/ownership/lineage/freshness/`contract_version`.
It honors the JEG-331 ground truth (per-view coverage metadata with
explicit "not available for this combo" semantics, versioned extension
points for the JEG-329 rework). It carries per-row VALUE PROVENANCE and
`tier_price_vector` for vector+blend bench share. The bench-share bounds
(default 0.15, user-settable, bounded [0.01, 0.30]) ship on
`api.product_options`. The publish gate verifies `pie_vintage == bake_id`
and `tier_price_vintage == bake_id`. `contract_version` is `1.0.0`;
unknown versions fail-closed. `product-data.js` is the single FE
adapter. Phase D sequencing and Phase E computation ownership are
recommendations for Jeremy's call. The recommendation for JEG-325 is
re-scope as JEG-327 Phase D.