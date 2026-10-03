# JEG-208 — Monitoring Dashboard Audit

**Lane:** minimax (M3)
**Branch:** minimax/jeg-208-audit
**Date:** 2026-10-02
**Subject:** modules/dashboard.html alignment with the three-view architecture
**Scope:** Read-only analysis. No source files modified.

## Three-view architecture (the reference frame)

The three views were defined on 2026-10-02 (commit 63a884b, JEG-210) and are
exposed on the chart via a toggle. As documented in
`app/trade-value-chart/assets/curve-widget.js` (lines 784–810):

- **Indexed** — trade-value publishers only (FantasyPros, USA Today, CBS,
  FantasyCalc). No VORP. The current data-backed mode.
- **Value above waivers** (a.k.a. "VORP view") — every source in value-above-waivers
  units. Pending data via JEG-182 / JEG-206 / JEG-207.
- **Adjusted values** — every source through the shared weighting model.
  Pending data.

Today, only the **Indexed** view renders data; the other two show a
"This view is coming soon" placeholder.

The chart's view toggle is the consumer-facing expression of this
architecture. The monitoring dashboard (modules/dashboard.html) is the
operator-facing expression of the same pipeline and therefore should
describe its sections in the same vocabulary.

---

## What "alignment" means here

For each methodology-sensitive dashboard section, the audit asks:

| Question | Indexed view | VORP view | Adjusted view |
|---|---|---|---|
| Which sources should appear? | Trade-value publishers only | All sources | All sources |
| What transformation is shown? | Native → Indexed (0–70) | Native → Imputed VORP | Native → Indexed → Reweighted |
| What does "fidelity" mean? | Pre-indexed native == publisher | Imputed VORP == native × alloc factor | Reweighted == indexed × reweight mult |

The current dashboard is overwhelmingly an **Indexed-view** dashboard. Almost
every section describes the reindexing transformation. Only the lineage table
(the section JEG-207 just touched) has started to mention the VORP view's
columns, and the Adjusted view is essentially unaddressed.

---

## Section-by-section audit

The dashboard declares the following methodology-sensitive cards. Each is
audited below.

### 1. VORP translation freshness

**Current state** (`modules/dashboard.html:166–178`):
- Single status pill rendered from `data.vorp_translation` (built by
  `pipelines/build_pipeline_checkpoints.py`).
- Shows "n_ok / n_expected grains at current week via vorp-supabase".
- Description names the JEG-64 quantile mapping, the Wed 06:30 CT weekly
  refresh, and the chain's `translate_via_vorp` stage.

**Alignment with three-view architecture:**
- This section is **explicitly VORP-view**: it describes the freshness of the
  VORP-translated grains in Supabase that will eventually feed the
  value-above-waivers chart view.
- It does not yet distinguish between VORP-view sources (all) and
  Indexed-view sources (publishers only). Today every source's grain
  freshness is lumped into one `n_ok / n_expected` count.
- It does not mention the Adjusted view at all.

**Gaps:**
1. The freshness count is aggregate across the full source list, so the
   reader cannot tell whether the Indexed view (the only data-backed one)
   is ready or only the VORP view.
2. The "Bad = on reindex-fallback as its steady state" verdict conflates
   pipeline health (fallback reindex path) with VORP-view readiness. A
   source that is intentionally not VORP'd (e.g. ESPN, CBS ROS, Razzball
   per the lineage method note in `dist/modules/source-value-lineage.json`)
   should not appear in the VORP count at all — it is an Indexed-view
   source.
3. No separate column/count for Adjusted-view readiness.

**Recommended follow-ups (do NOT change here):**
- File JEG-209 (or similar): split the `vorp_translation` status into
  per-view counts (`indexed_ready`, `vorp_ready`, `adj_ready`), with the
  Indexed count only over the four trade-value publishers.
- Update the description to state explicitly: "VORP-view freshness only;
  the Indexed view uses trade-value publishers and does not require VORP
  translation."
- Add an `adj_view` status mirroring the VORP one once the Adjusted data
  pipeline lands.

---

### 3. Scale agreement

**Current state** (`modules/dashboard.html:180–193`):
- Verdict table per source × position: "agreement" / "genuine disagreement" /
  "indexation artifact", using the 0.80–1.25x band from the chart's
  `sourceScaleAgreement` guard.
- Source list is `["fantasypros", "usatoday", "fantasycalc", "cbs",
  "cbsros", "razzball"]` — note: includes CBS ROS and Razzball even though
  they have no published trade-value charts, and excludes ESPN.
- Rendered from `scale-agreement.json` via fetch, **not** from
  `pipeline-checkpoints.json`. The section status flows into the headline
  count via `data.scale_agreement.status`.

**Alignment with three-view architecture:**
- **Indexed view**: this section *is* the Indexed-view scale check. It
  compares the publisher's native curve against the ESPN anchor and
  against our reindexed curve. That is exactly what the Indexed view
  shows the reader. ✓
- **VORP view**: the section is silent on the VORP scale. VORP is a
  unitless replacement-tier-difference; comparing a publisher's VORP shape
  to an ESPN VORP shape is meaningful, but the verdict vocabulary
  ("agreement", "indexation artifact") was written for indexed values.
- **Adjusted view**: not addressed.

**Gaps:**
1. The source list includes CBS ROS and Razzball (DDF sources that the
   JEG-210 Indexed view explicitly excludes — see `AS_PUBLISHED_KEYS` in
   `curve-widget.js`). The dashboard's source list and the chart's
   Indexed-only source list disagree.
2. The verdict vocabulary is Indexed-view-shaped. For the VORP view it
   should speak in VORP units (e.g. RB waiver line value); for the
   Adjusted view it should speak in reweight-multiplier terms.
3. Band 0.80–1.25x is the Indexed-view band. VORP and Adjusted views
   need their own bands; the section does not say so.

**Recommended follow-ups:**
- File JEG-211 (or similar): tighten the scale-agreement source list to
  `AS_PUBLISHED_KEYS` (FantasyPros, USA Today, CBS, FantasyCalc) and
  mark CBS ROS / Razzball as "not applicable" rows so the section's
  scope matches the chart's Indexed view.
- Add a parallel VORP-view scale check (imputed_VORP shape vs a group
  VORP anchor) and an Adjusted-view scale check (reweight_multiplier
  variance).

---

### 4. Source fidelity — pre-indexed values

**Current state** (`modules/dashboard.html:195–205`):
- Compares the pipeline's pre-indexed (native) per-game projections against
  the source data; requires **exact match**.
- Source order: `["espn", "cbs", "cbsros", "razzball", "fantasycalc",
  "fantasypros", "usatoday"]` — every source.
- Rendered from `source-fidelity.json`.

**Alignment with three-view architecture:**
- **Indexed view**: this is the Indexed-view fidelity check. Native must
  match the publisher's published number. ✓
- **VORP view**: silent. The VORP-view equivalent would be: "imputed VORP
  == native × alloc factor", which is exactly what JEG-207 just added to
  the lineage table as the `imputed_vorp` column. There is no separate
  VORP-fidelity section that fails red when the multiplication does not
  hold.
- **Adjusted view**: silent.

**Gaps:**
1. No VORP-fidelity check. If `alloc_factor` or `our_group_vorp` is wrong
   for a source, only the lineage section shows it; the headline count
   does not include a VORP-failure status.
2. No Adjusted-fidelity check. If the reweight multiplier is wrong, the
   only place it shows up is the lineage table's "Rewgt mult" column.
3. The source order mixes Indexed-view publishers with non-publisher
   sources (ESPN, CBS ROS, Razzball). For the Indexed view those rows
   should not be here at all — ESPN has no published trade value to match.

**Recommended follow-ups:**
- File JEG-212 (or similar): rename this section to "Source fidelity —
  Indexed view (pre-indexed natives)" and restrict the source list to the
  four trade-value publishers.
- Add a parallel "Source fidelity — VORP view (native × alloc factor ==
  imputed VORP)" section that pulls the JEG-207 columns into a fail/pass
  check.
- Add a parallel "Source fidelity — Adjusted view (indexed × reweight
  mult == chart)" section.

---

### 6. Index math — raw to indexed transformation

**Current state** (`modules/dashboard.html:221–229`):
- Recomputes the native → indexed step and compares against the actual
  indexed value; requires exact match.
- Source order same as Source fidelity (all sources).
- Rendered from `index-math.json`.

**Alignment with three-view architecture:**
- **Indexed view**: ✓ this is the Indexed-view math verification. The
  column heading reads "native → recomputed → actual" which is exactly
  the Indexed transformation.
- **VORP view**: silent. The VORP math would be "native → × alloc factor →
  imputed VORP" (the Option C method JEG-207 added).
- **Adjusted view**: silent. The Adjusted math would be "indexed →
  × reweight mult → reweighted".

**Gaps:**
1. The section's title says "raw to indexed" but the section is actually
   a generic transformation check. It could host the VORP and Adjusted
   transformations too, but it doesn't.
2. Source order includes ESPN/CBS ROS/Razzball whose "indexed" value is
   not a trade-value reindex (it's a DDF leg output). For ESPN the
   transformation is *value-above-waivers*, not *native → indexed*. The
   section does not flag this.

**Recommended follow-ups:**
- File JEG-213 (or similar): split this into three subsections, one per
  view, or add a view selector so the same card shows the right
  transformation for each view.
- For the Indexed view, restrict the source list to the four trade-value
  publishers. For the VORP view, show the Option C multiplication. For
  the Adjusted view, show the reweight multiplication.

---

### 5. Source value lineage — top 25 players per source (JEG-207)

**Current state** (`modules/dashboard.html:231–247`):
- The only section that touches all three views at once. Renders per
  source: Live, Native, **Group**, **Our group VORP**, **Alloc factor**,
  **Imputed VORP**, DDF rebuilt, Idx mult, Indexed, Rewgt mult,
  Reweighted, Chart.
- Source order is parent → adjusted leg, parent → adjusted leg, … (JEG-98).
- The JEG-207 diff added: Group, Alloc factor, Our group VORP, Imputed VORP
  as the Option C columns. Implied VORP (legacy) was removed from the
  visible columns but the data field is still present in the JSON
  (`implied_vorp` still appears on `dist/modules/source-value-lineage.json`
  even though the dashboard no longer renders it).
- The Adjusted view's columns (`indexed`, `reweight_mult`, `reweighted`)
  are present but only populated for sources with an adjusted leg.

**Alignment with three-view architecture:**
- **Indexed view**: the Indexed-view transformation chain is fully
  rendered (Native → Indexed via index_mult → Chart). ✓
- **VORP view**: the VORP-view columns (Group, Our group VORP, Alloc
  factor, Imputed VORP) are now rendered per row. ✓ — this is the section
  JEG-207 just improved.
- **Adjusted view**: the columns are there but mostly empty for non-leg
  sources. The reweight transformation is rendered for the four adjusted
  legs only.

**Gaps:**
1. **Implied VORP is still produced** (`implied_vorp` field on every
   `top25` entry in `dist/modules/source-value-lineage.json`) but the
   dashboard no longer renders it. JEG-207's commit dropped the
   "Impl. VORP" column from the table, but the pipeline still computes
   the old value. This is dead data.
2. **Alloc factor is computed on placeholder group VORP** when JEG-206
   output is absent (the column description explicitly says so). The
   lineage card has no signal that a placeholder is in use. A reader
   looking at "Alloc factor = 1.02x" cannot tell if that is the real
   group total or a 1:1 placeholder.
3. **No view-mode label.** The card does not say "this row shows the
   Indexed-view chain here, the VORP-view chain there, the Adjusted-view
   chain in those columns." A new operator has to read the tooltips to
   understand which column belongs to which view.
4. **No pass/fail for the VORP-view chain.** If
   `imputed_vorp != native × alloc_factor`, nothing turns red. The
   dashboard asserts the Indexed chain (Chart ✓) and the Live ✓ chain,
   but not the VORP chain.
5. **No pass/fail for the Adjusted-view chain** beyond "Chart ✓".

**Recommended follow-ups:**
- File JEG-214 (or similar):
  1. Add a view-mode legend at the top of the lineage card that groups
     the columns: "**Indexed view**: Native → Indexed → Chart ·
     **VORP view**: Native × Alloc factor → Imputed VORP · **Adjusted
     view**: Indexed × Rewgt mult → Reweighted."
  2. Add a VORP-fail red ✗ when `imputed_vorp != native × alloc_factor`
     (within a tolerance), with the message shown on hover.
  3. Add an Adjusted-fail red ✗ when `reweighted != indexed × reweight_mult`.
  4. Mark placeholder group VORP rows with a distinct icon and a banner
     "JEG-206 output absent; alloc factor = 1.0 by default."
  5. Remove `implied_vorp` from the lineage pipeline output entirely
     (dead data), or move it behind a debug toggle.

---

### 2. Methodology consistency

**Current state** (`modules/dashboard.html:156–164`):
- Asserts "all as-published sources must use the same reindex method and
  anchor at each transformation step."
- Single pill rendered from `data.methodology_consistency`.

**Alignment with three-view architecture:**
- **Indexed view**: ✓ this is the Indexed-view methodology check. Reindex
  method + anchor uniformity is exactly the Indexed-view invariant.
- **VORP view**: silent. The VORP-view methodology invariant is "every
  source uses the same 8-group totals" (the Option C input from JEG-206).
- **Adjusted view**: silent. The Adjusted-view methodology invariant is
  "every source uses the same reweight model."

**Gaps:**
1. The section does not state that it is Indexed-view-only.
2. No equivalent checks for the VORP view (8-group uniformity) or the
   Adjusted view (reweight model uniformity).

**Recommended follow-ups:**
- File JEG-215 (or similar): rename this section to "Methodology
  consistency — Indexed view" and add parallel "Methodology consistency —
  VORP view" and "Methodology consistency — Adjusted view" sections.
- The VORP-view check should fail red if two sources have different
  `our_group_vorp` for the same group (only meaningful when JEG-206 is
  present — placeholder state should be reported separately).

---

## Top 3 gaps

1. **The dashboard is an Indexed-view dashboard with three-view vocabulary
   missing.** Most sections describe the Indexed transformation in
   Indexed-view language without ever naming which view they belong to.
   The chart's three-view toggle (JEG-210) makes the view vocabulary
   available to readers; the dashboard should adopt it too.

2. **VORP-view and Adjusted-view sections do not exist as separate
   artifacts.** The lineage card is the only place where VORP columns are
   rendered (thanks to JEG-207), and the Adjusted columns appear only as
   empty cells. There is no per-view pass/fail headline count, no
   per-view scale-agreement check, and no per-view methodology
   consistency check.

3. **The lineage card has no VORP-view or Adjusted-view pass/fail.** Even
   with the Option C columns rendered, a wrong `alloc_factor` or a wrong
   `reweight_mult` does not turn red. A reader has to do the arithmetic
   in the tooltips. JEG-207 added the columns but not the assertion.

---

## What I could not verify

- **The live `dist/modules/source-value-lineage.json`** does not yet contain
  the JEG-207 Option C fields (`imputed_vorp`, `alloc_factor`,
  `our_group_vorp`, `group`). I grep'd the file and got zero matches; the
  top-25 entries still carry `implied_vorp`, `vorp_replacement_level`,
  `vorp_inferred_position`, `vorp_inferred_n_rostered` (the pre-JEG-207
  shape). The dashboard's HTML was updated in JEG-207, but the JSON
  generator has not been re-run since — or the `dist/` copy is stale.
  I did not run any pipeline to confirm which is the case; this is a
  read-only audit. The pipeline file `pipelines/build_source_value_lineage.py`
  does contain 25 occurrences of those field names, so the build script
  *can* produce them. Recommend re-running the build before the next
  dashboard deploy and verifying the columns appear in `dist/`.
- **The `AS_PUBLISHED_KEYS` set** I cite from `curve-widget.js` is not
  confirmed by reading the full file; I saw it referenced in the
  JEG-210 commit diff context. A future audit could double-check it.
- **The three-view architecture** is documented in
  `app/trade-value-chart/assets/curve-widget.js` (the
  `VIEW_MODE_DEFS` block). There is no separate architecture document at
  the time of this audit. The task brief states the three views were
  "defined 2026-10-02" which matches the JEG-210 commit timestamp; the
  curve-widget code is the de-facto spec.
- **I did not run any pipeline or test.** This is analysis only. The
  runtime state of `data.vorp_translation`, `scale-agreement.json`,
  `source-fidelity.json`, `index-math.json`, `source-value-lineage.json`
  was inspected as static files where relevant.

---

## Sections audited

- Methodology consistency
- VORP translation freshness
- Scale agreement — native vs reindexed vs anchor
- Source fidelity — pre-indexed values
- Source fidelity — end to end (live vs dashboard) — read but not deeply
  audited; it is a freshness + ordering check that sits across all three
  views and does not pick one
- Index math — raw to indexed transformation
- Source value lineage — top 25 players per source

## Sections not audited (out of scope per task brief)

- Fleet health — 10 checkpoints
- Data flow — 10 checkpoints
- Deployment — live verification
- GitHub Actions — workflow health
- Adjusted curves — pipeline stages (the A1–A5 chain itself; only its
  relationship to the three views noted)
- Player Trace — end-to-end value path
- Aggregate Diagnostics — anomalies & curve health
- ESPN input verification — grain-to-grain
- ESPN raw trade values — unscaled DDF output
- Trade dashboard QA — rendered output health
- ESPN-zero staleness signal
- Cross-source agreement — systematic divergence detection
- Identity resolution — player_key join verification

These are operational, freshness, or QA sections; the audit task scoped
itself to the six methodology-sensitive sections listed above.