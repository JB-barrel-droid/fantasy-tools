# Consolidation Layer — Scope

**Status:** Draft for Jeremy's review. No implementation until approved.
**Date:** 2026-10-03 (revised with Codex input + week-dimension requirement)
**Context:** Jeremy's Excel model has three layers — detail tabs (machinery), a consolidation tab (final numbers, no logic), presentation tabs (polished views). This scope applies that pattern to the trade value data architecture.

> Note: Codex was tasked with this scoping work but stalled with zero output after 16+ minutes and was terminated. This document was written directly from verified repo state (fixture inspected 2026-10-03). A subsequent Codex review (consolidation-layer-codex-review.md) provided input incorporated below.

---

## Goals

1. **Single source of truth:** Exactly one final value per player per source per week per scoring/teams/view. If the chart and calculator disagree, the bug is in presentation, never in data.
2. **Separation of concerns:** Detail layer (build logic, provenance, lineage, fit params) stays rich. Consolidation layer is dumb and flat — just the numbers. Presentation layer reads only from consolidation.
3. **Debuggability:** When values are wrong, you know which layer to look in. Detail bug = build problem. Consolidation mismatch = bake problem. Presentation disagreement = UI problem.
4. **No disruption:** Detail layer continues as-is. Migration is strangler-fig — consolidation ships alongside, consumers migrate one by one.
5. **Fail-closed:** Consolidation bake verifies against detail (SHA match + row reconciliation). If they diverge, the build fails, never silently serves wrong numbers.
6. **Easy auditability:** Given any value on the chart, trace it back through consolidation to the exact detail-layer inputs. No black boxes. Pick any number → consolidation row → detail bake → source data.
7. **Week-over-week tracking:** Prior weeks' data lives in consolidation. Easy to track changes week-to-week by source. Clear which week and source each column/value belongs to.

---

## 1. What the consolidation layer is

A dumb, flat store of **final calculated values**: every player × every source × every week × every scoring/teams combo × every view. No build logic, no provenance metadata, no intermediate state. Just the numbers presentation tools need to render.

**"Final" means:**

| Included | Why it's final |
|---|---|
| `reindexed` values per (source, week, combo) | The chart-ready numbers after indexation onto the anchor pie. This is what the chart, calculator, and trade designer display. |
| `vorp_views` (indexed / vorp / adj_values) per (source, week) | The JEG-242 VORP translation outputs — already-promoted, already-verified final values for fantasycalc, fantasypros, usatoday. |

**Excluded from "final" (stays in detail):** `native` values (pre-indexation — useful for audit, not display), `fit` parameters (adjustment cell alpha/beta — build inputs, not outputs), `index_total` bucket detail (how the pie was allocated — audit trail).

**Scale:** ~18,626 reindexed cells + ~1,894 vorp_views cells ≈ 20,500 rows **per week**. With 4 weeks retained: ~82,000 rows. Trivial for JSON or Postgres. The current detail fixture is 2.8MB; a flat consolidation would be a fraction of that per week (no bucket detail, no lineage text, no fit params).

**Week dimension:** Each row carries `week` (NFL week number, 1-18) and `season` (e.g., 2026). This enables week-over-week tracking: query all rows for player P, source S, weeks 1-4 to see the trend. The consolidation artifact retains the last N weeks (N=4 default, configurable) — older weeks age out as new bakes land.

---

## 2. What it is NOT

**Not a replacement for the detail layer.** `comparison-sources-data.json` keeps its full rich structure: per-source lineage, `claimed_settings`, `provenance_note`, fit parameters, `index_total` bucket breakdowns (pre/post totals, scales, anchors), `espn_zeroed` flags, `source_validation`, `value_weeks`, `_jeg242_transform` metadata. All of that exists for audit, debugging, and rebuilds — the consolidation layer must never become the system of record for *how* a number was produced.

**Not presentation logic.** No sorting, no filtering, no display formatting, no trade math (e.g., "fair trade" calculations stay in the chart app). No per-user state. The consolidation layer answers one question: "what is player P's final value from source S under scoring/teams/view V?" Nothing else.

**Boundary test:** if removing a field would break an audit or a rebuild, it stays in detail. If removing a field would break a rendered number, it belongs in consolidation. Fields needed by both live in both (detail is authoritative; consolidation is derived — see §7).

---

## 3. Schema

### Supabase as primary store, JSON as served artifact

**Decision (Jeremy 2026-10-03):** Build the consolidation layer in Supabase as the system of record. The bake writes rows to `public.consolidated_values`; a JSON export is generated for the static site.

Rationale:
- The week dimension makes this a time-series — SQL querying ("Allen's FantasyCalc values weeks 1-4") is natural; JSON filtering is clunky.
- Supabase is already the platform (JEG-285 scheduling, JEG-322 monitoring) — consolidation fits that direction.
- Auditability (Goal 6) is stronger with SQL: join consolidation rows to detail metadata, filter by week/source, spot anomalies.

**Table:** `public.consolidated_values`

```sql
CREATE TABLE public.consolidated_values (
  player TEXT NOT NULL,           -- canonical lowercase key
  source TEXT NOT NULL,           -- 11 source keys verbatim
  season INT NOT NULL,            -- e.g., 2026
  week INT NOT NULL CHECK (week BETWEEN 1 AND 18),
  scoring TEXT NOT NULL CHECK (scoring IN ('full', 'half', 'standard')),
  teams INT NOT NULL CHECK (teams IN (8, 10, 12, 14)),
  qb_variant TEXT CHECK (qb_variant IN ('qb1', 'qb2')),  -- NULL except fantasycalc
  view TEXT NOT NULL,             -- 'combo_reindexed' | 'vorp_indexed' | 'vorp' | 'adj_values'
  value NUMERIC NOT NULL,         -- exact, no rounding
  detail_locator TEXT NOT NULL,   -- deterministic path in detail fixture
  bake_id TEXT NOT NULL,          -- which bake produced this row
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (player, source, season, week, scoring, teams, qb_variant, view)
);
```

**Weeks retained:** ALL weeks (Jeremy 2026-10-03). No aging out. The table accumulates full history — every week, every source, every player. Storage is trivial (~20k rows/week).

**JSON export:** `pipelines/export_consolidated_json.py` generates `consolidated-values.json` from the table for the static site. The JSON includes filters and ease-of-use features:
- Pre-indexed by (player, source, week) for O(1) lookups
- `weeks_available` array at the top (which weeks have data)
- `sources_available` per week (which sources priced that week)
- Minified for dist; pretty-printed for the committed fixture (diff readability)

**RLS:** Enabled. Public read (the chart needs it); writes restricted to service role (bake process only).

### Proposed JSON schema

```json
{
  "schema": "consolidated-values-v1",
  "bake_id": "ddf-20261003-espn-ppr-12t-0p15",
  "detail_sha256": "<sha256 of the comparison-sources-data.json this was derived from>",
  "generated_at": "2026-10-03T22:00:43Z",
  "season": 2026,
  "weeks_retained": [1, 2, 3, 4],
  "vintages": {
    "fantasycalc": "2026-10-03",
    "espn": "2026-10-03"
  },
  "rows": [
    {
      "player": "josh allen",
      "source": "fantasycalc_adjusted",
      "season": 2026,
      "week": 4,
      "scoring": "full",
      "teams": 12,
      "qb_variant": "qb1",
      "view": "reindexed",
      "value": 25.4,
      "detail_locator": "sources.fantasycalc_adjusted.combos.full_12_qb1.reindexed['josh allen']"
    }
  ]
}
```

### Column/key decisions

- **player:** canonical lowercase key from the project's naming table (the IdentityMap). Fail-closed: a player that doesn't resolve to a canonical key is excluded from consolidation and logged — never guessed. (Standing rule: identity resolved before any pricing/display logic.)
- **source:** the 11 source keys verbatim (`fantasycalc_adjusted`, `cbsros`, etc.). No renaming.
- **season:** integer (e.g., 2026). Enables multi-season retention if needed.
- **week:** integer 1-18 (NFL week). The consolidation retains the last N weeks (default 4). Each bake appends the current week's rows; weeks older than N age out.
- **scoring:** `full` | `half` | `standard` (matches the combo-key vocabulary in `value-model.js`).
- **teams:** integer 8 | 10 | 12 | 14.
- **qb_variant:** `"qb1"` | `"qb2"` | `null`. Non-null **only** for `fantasycalc` / `fantasycalc_adjusted` — every other source gets `null`. This mirrors the `sourceComboKey()` logic exactly (which appends `_qbN` only for fantasycalc). The flat schema makes the special case explicit instead of hiding it in a string suffix.
- **view:** `"reindexed"` (from combos) | `"indexed"` | `"vorp"` | `"adj_values"` (from vorp_views). Note the naming collision risk: `vorp_views.indexed` vs combo `reindexed` are different things (native-indexed VORP input vs pie-indexed chart values). Per Codex recommendation, consider renaming to `"vorp_indexed"` vs `"combo_reindexed"` before v1 — cheapest to do now.
- **value:** number, **exact** as computed in detail (no rounding). Per Codex: rounding belongs in presentation, not consolidation. Rounding breaks strict reconciliation, calculator consistency, and the single-value claim.
- **detail_locator:** deterministic path to the source value in the detail fixture (e.g., `"sources.fantasycalc_adjusted.combos.full_12_qb1.reindexed['josh allen']"`). Per Codex: file-level `detail_sha256` is necessary but not sufficient for auditability (Goal 6). Each row needs this locator so "pick any number and trace it" works.

### Zero vs missing vs unsupported (per Codex)

- **Zero:** `value: 0` with explicit flag (e.g., `espn_zeroed: true` in detail). A real zero from IR zero-out.
- **Missing:** no row exists. Player not priced by this source this week.
- **Unsupported:** tuple not in the manifest (e.g., CBS doesn't do 8-team). The consolidation includes a tuple manifest; lookups for unsupported tuples return null (never fall back to another tuple).

### Versioning

- `schema`: `"consolidated-values-v1"` — bump on any breaking shape change.
- `bake_id` + `detail_sha256`: tie every consolidation artifact to the exact detail fixture it was derived from. A consolidation file whose `detail_sha256` doesn't match the served detail fixture is stale by definition.
- `vintages`: per-source content vintage dates (not pull times — standing freshness rule).

### Row count estimate

18,626 reindexed + 1,894 vorp_views ≈ **20,520 rows per week**. With 4 weeks retained: ~82,000 rows. At ~150 bytes/row as JSON (with detail_locator), ≈ 12MB unminified for 4 weeks. Acceptable for a static site artifact; minified JSON shrinks it further. If size becomes a concern, array-of-objects can switch to array-of-arrays (per Codex recommendation for the canonical fixture).

---

## 4. Build process

**New pipeline stage:** `pipelines/build_consolidated_values.py`, run as the **last step** of the comparison bake (after the fixture is written and validated, before deploy).

**Trigger:** the existing GitHub Actions `rebuild-chain.yml` (every 6h). The consolidation build is a pure derivation — it reads the just-baked `comparison-sources-data.json` and emits `consolidated-values.json`. It adds seconds, not minutes.

**Failure semantics — fail closed:**
- If the detail fixture fails validation, consolidation is not built (nothing to derive from).
- If consolidation derivation fails or reconciliation fails (§7), the bake fails. A half-built consolidation must never ship — presentation would show a mix of fresh detail and stale/missing consolidation.
- The deploy gate (`make validate`) gains a check: `detail_sha256` in the consolidation artifact must match the sha256 of the shipped detail fixture. Mismatch = blocked deploy.

**Not triggered by:** the 30-min dashboard push (that's health monitoring, not a rebuild — it must never regenerate consolidation). Manual on-demand runs are allowed for debugging but the output is not pushed without a full bake.

**Where artifacts live:**
- Build output: `output/consolidated-values.json`
- Fixture (committed): `data/fixtures/current/consolidated-values.json`
- Served copies: `dist/consolidated-values.json`, `dist/modules/consolidated-values.json` (if the monitor needs it — see open questions), `app/trade-value-chart/assets/consolidated-values.json`

---

## 5. Migration path

### Current read paths (to be replaced)

- `comparison-dashboard.js`: `data.sources[key].combos[comboKey].reindexed[player]` (deep path, combo-key construction via `ValueModel.sourceComboKey`)
- `curve-widget.js`: `combo?.values || combo?.reindexed` then per-player lookup

### Proposed read path

```js
// Before (detail):
const combo = data.sources?.[sourceKey]?.combos?.[comboKeyFor(sourceKey)];
const value = combo?.reindexed?.[playerKey];

// After (consolidation):
const value = consolidation.lookup({player: playerKey, source: sourceKey,
  scoring, teams, qbVariant, view: 'reindexed'});
```

A small `ConsolidationIndex` (built once at load: nested Map or a single Map keyed by `player|source|scoring|teams|qb|view`) replaces the deep-path traversal. Lookup becomes O(1) with no knowledge of the detail schema.

### Strangler-fig sequence

1. **Ship consolidation alongside detail** (no consumer changes). Bake produces both; reconciliation test proves equality (§7). This step alone is safe and reversible.
2. **Migrate `curve-widget.js` first.** It's the simpler consumer (reads one combo's reindexed dict). Behind a flag or just directly — if reconciliation is green, the values are identical by construction.
3. **Migrate `comparison-dashboard.js`.** Larger surface (combo existence checks, `sourceComboExists`, per-source iteration). Migrate read-by-read; the dashboard's `state.combos` bookkeeping stays (it tracks *which* combos exist — that's UI state, not values).
4. **Delete detail read paths** from presentation code once both consumers are migrated and the deploy gate has held for one full rebuild cycle. The detail fixture continues to ship (it's the audit layer and the monitor may still want it).

**Provider-atomic migration (per Codex):** Each feature uses detail OR consolidation — never silent per-value fallback. A fallback would hide missing rows and break fail-closed. During migration, shadow-compare (run both, log divergences), expose the active provider + bake ID in the UI (for debugging), and retire old paths on coverage evidence, not "one rebuild cycle."

### What does NOT change

- Combo-key vocabulary (`full_12_qb1` etc.) remains the UI's language for "which league settings" — the consolidation lookup just takes the decomposed parts.
- The `sourceComboKey()` exact-identity rule (never borrow another league size/QB grain) is preserved: the lookup returns null for nonexistent (source, scoring, teams, qb) tuples instead of falling back.

---

## 6. What stays in detail

Everything in `comparison-sources-data.json` that is not a final display number stays. Explicitly:

| Stays in detail | Why presentation doesn't need it |
|---|---|
| `native` values per combo | Pre-indexation raw values; audit input, not display |
| `fit` (adjustment cell alpha/beta, n, x_mean, y_mean) | Build parameters for the as-published adjustment refit; needed to re-derive, not to display |
| `index_total` bucket detail (per-position pre/post totals, scales, anchors) | Proves the pie allocation was correct; audit trail |
| Per-source `lineage`, `provenance_note`, `claimed_settings`, `value_provenance` | Source honesty layer; the monitor dashboard and docs consume these, not the chart |
| `espn_zeroed` flags | IR zero-out audit; chart just shows the 0 |
| `source_validation`, `value_weeks`, `player_keys` | Pipeline health metadata |
| `_jeg242_transform` (batch70 schema, batch_sha256, per-source promote/skip status) | VORP promotion audit trail |
| `built_at`, `display`, `teams` top-level metadata | Bake metadata |
| `adjustment-inputs.json` (separate artifact) | The refit inputs; consolidation is downstream of these |

The detail fixture remains the **system of record**. Consolidation is a derived, disposable projection — it can always be rebuilt from detail.

---

## 7. Testing

### Reconciliation: the core guard

`pipelines/build_consolidated_values.py` ends with a self-check: for every row emitted, re-read the value from the detail fixture via the *original* path (`sources[s].combos[c].reindexed[p]` / `sources[s].vorp_views.views[v][p]`) and assert strict equality. Any mismatch = build failure, nothing ships.

**Bidirectional key-set reconciliation (per Codex):** Row counts alone can't catch a missing row offset by a duplicate. Validate the exact composite primary key `(player, source, season, week, scoring, teams, qb_variant, view)`:
- No missing rows (every derivable detail cell has a consolidation row)
- No extra rows (every consolidation row traces to a detail cell)
- No duplicates (composite key is unique)
- No invalid tuples (every (source, scoring, teams, qb_variant) tuple is in the manifest)

### Discrimination test (standing rule)

Per the project's rule — *a guard must prove it catches the bug it names* — add `tests/test_consolidation_reconciliation.py` with:

1. **Positive:** build consolidation from a real fixture, assert every row reconciles (guards the happy path).
2. **Negative (simulated broken state):** corrupt one consolidation row (e.g., change a value by 0.1), assert the reconciler fails. Corrupt the `detail_sha256`, assert the deploy gate fails. Drop a row, assert the key-set check fails (not just row count). Add a duplicate row, assert the uniqueness check fails.
3. **Schema:** assert every row has exactly the v1 keys; assert `qb_variant` is non-null **iff** source is fantasycalc/fantasycalc_adjusted (the special-case invariant); assert `week` is in 1-18; assert `value` is exact (not rounded).
4. **Audit:** assert every row has a valid `detail_locator` that resolves to the correct detail path.

### Deploy gate additions (`make validate`)

- `consolidated-values.json` exists and parses.
- `detail_sha256` matches the shipped `comparison-sources-data.json`.
- Row count equals the detail fixture's derivable cell count (18,626 + 1,894 as of 2026-10-03; computed dynamically, never hardcoded — standing rule: guards derive from registries, never hardcode counts).
- The pinned-value test (`test_known_full_ppr_12_team_source_values`) continues to pass against the detail fixture — consolidation doesn't replace it, it adds a second layer that must agree.

### What "green" means

Reconciliation green + deploy gate green = consolidation is a faithful projection of detail. Presentation bugs then localize to presentation code, which is the entire point of the layer.

---

## 8. Open questions for Jeremy

1. **JSON only, or Supabase mirror too?** Recommendation is JSON first (§3). Codex agrees for phase 1, but notes: design the schema so it maps cleanly to a table later (which the flat column design does). Is there any server-side consumer on your mind that would need the Supabase table now, or is JSON-only fine until one appears?
2. **Do `native` (pre-indexation) values belong in consolidation?** They're currently display-adjacent in one place: `curve-widget.js` line 743 comments that native values are "the source's own" numbers shown somewhere. Codex: inventory every presentation read first — if anything displays/computes from `native` values they must be included (otherwise Goal 1 is violated). Otherwise they stay detail-only.
3. **Should the monitor dashboard (`modules/dashboard.html`) read consolidation?** The monitor currently reads health/checkpoint JSONs, not player values. Codex: yes — the monitor should validate the *served* consolidation artifact end-to-end (live publisher values → detail → consolidation → rendered). This would be a genuinely good end-to-end check.
4. **The `indexed` vs `reindexed` naming collision** (§3): `vorp_views.indexed` (native-indexed VORP input) vs combo `reindexed` (pie-indexed chart values) are different numbers that both contain "indexed". Codex recommends renaming now before v1 (cheapest): `"vorp_indexed"` vs `"combo_reindexed"`, or add a `value_family` dimension. Accept the rename?
5. **Row layout:** array-of-objects (readable, ~12MB for 4 weeks) vs array-of-arrays (smaller, less readable)? Codex recommends array-of-objects for the canonical fixture. JSON is minified in dist either way; this only affects the committed fixture's diff readability.
6. **Weeks retained:** Default is 4 weeks. Enough for week-over-week tracking, or do you want more history? (Storage is trivial — 20k rows/week.)
7. **Week-over-week UI:** Should the chart/dashboard get a week-selector to view prior weeks' values, or is the week dimension purely for data tracking/debugging for now?

---

## Decision needed

Approve / revise / reject:

- [ ] The three-layer model (detail → consolidation → presentation) as the target architecture
- [ ] JSON-first consolidation artifact (`consolidated-values.json`, schema v1 as proposed)
- [ ] Build as final stage of the comparison bake, fail-closed with reconciliation
- [ ] Strangler-fig migration: ship alongside → migrate curve-widget → migrate dashboard → delete old read paths
- [ ] Answers to the 5 open questions above (or "your recommendation is fine" for any of them)

**Explicit non-goals for this scope:** no Supabase table until a consumer exists; no changes to the detail fixture's schema; no methodology changes (indexation, VORP translation, adjustment refit all untouched — this is plumbing, not math); no presentation redesign.
