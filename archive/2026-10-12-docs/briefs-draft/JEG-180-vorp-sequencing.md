# JEG-180 — VORP translation sequencing: subtract waiver line only after stripping publisher economics

Lane: minimax (M3)
Branch: minimax/jeg-180-brief
Decision owner: Jeremy (methodology call — PENDING)
Draft-only: no code changes in this commit. Linear CLI unavailable in this sandbox.

---

## 1. Problem

`pipelines/vorp_translation/unified.py::translate_source` computes implied VORP
by subtracting the waiver line directly from the publisher's raw site values
*before* any starter/bench split or positional-weight normalization (`unified.py:228`).
The publisher's own positional weights and starter/bench curve shape are still
embedded at subtraction time, so what comes out is **not** a VORP in our
economic system — it is their finished values, shifted and stretched. Our
economics (cells, pie rescale) are then applied as patches that a single
straight-line cell per `(position, tier)` cannot fully correct, because the
contamination is non-linear across the curve (the chief example is FantasyCalc,
whose WR waiver line and RB waiver line live on different scales and shapes).

The tell is in the published spot-check: Jaxon Smith-Njigba on the
`fantasycalc_adjusted` path in `dist/modules/source-value-lineage.json` —
native `9914.0` → publisher waiver `16.0` (WR) → **implied_vorp `9898.0`**
→ indexed `55.0` → adjusted `40.0` (`source-value-lineage.json:4725`). The
`9898` is FantasyCalc's WR positional economy (compressed range, low
replacement), not ours; the cell at `(WR, starter)` then has to compress
`9898 → 55.0 → 40.0` and a straight-line affine map cannot undo a
non-linear shape distortion. Chase Brown and Jahmyr Gibbs show the same
pattern with RB-native thousands against RB-waiver 134 (`source-value-lineage.json:4511–4725`).
The fix is sequencing, not parameter tuning: subtraction must happen inside
one economic system.

## 2. Background — what exists today

### Stage order as currently coded

1. **Native load** — `pipelines/vorp_translation/unified.py:99-146`
   `load_native_values(source, scoring, teams)` returns `ranked[pos] = [(name, value)]`
   sorted descending per position; identity resolves through the naming table
   (`canonical_players.Registry`, standing rule 2026-10-02 / JEG-75) so
   `jaxon smithnjigba` matches `Jaxon Smith-Njigba`.
2. **Roster math (DDF-side)** — `pipelines/vorp_translation/vorp_via_roster.py:189-254`
   `rostered_for_teams(teams, bench_per_team, flex_count, ranked=ranked)` returns
   per-position `{dedicated, flex, bench, rostered}` slots under the SAME source's
   native rankings via `apportion` to L78-95 (highest-averages, deterministic) and
   `allocate_flex_vorp_weighted` to L98-163 (VORP-weighted flex using a
   slot-proportional waiver baseline).
3. **Waiver line (publisher-side, IN-MEMORY ONLY)** —
   `pipelines/vorp_translation/vorp_via_roster.py:257-274`
   `roster_waiver_line(ranked, n_rostered)` returns
   `ranked[n_rostered][1]` for `roster_determined`, else `ranked[-1][1]`.
   `unified.py:217-225` calls this *implicitly* via `players[n_rostered][1]`
   on the publisher's own ranked list. **This is the contamination step.**
4. **Subtraction runs on raw publisher rows** —
   `pipelines/vorp_translation/unified.py:228-229`:
   `vorp_list = [(pkey, name, val, max(0.0, val - waiver_val)) for ...]`.
   The result of step 4 is what `build_write_rows` (L292-352) sends to
   Supabase as `publisher_vorp.vorp_value`, and what the lineage monitor
   (`source-value-lineage.json` — see `vorp_inferred_position`,
   `vorp_replacement_level`, `implied_vorp` per row) labels `implied_vorp`.
5. **Translate → OUR_MAX (per-position affine map)** —
   `pipelines/vorp_translation/unified.py:230-243`: `scale = OUR_MAX[pos]/max_vorp`,
   then `translated = vorp × scale`. OUR_MAX is `{QB 25, RB 70, WR 55, TE 30}`
   (`unified.py:59-64`).
6. **Cells fit (stage 2)** — `pipelines/build_adjustment_inputs.py:303-375`
   `fit_cells(published, roles, leg_values, canonical)` does OLS per
   `(position, tier ∈ {starter, bench})` against the DDF two-tier leg
   (`build_adjustment_inputs.py:419-422`: DDF-native sources fit to themselves,
   trade-chart sources fit to the ESPN-pure leg). Identity fallback
   (`alpha=0, beta=1`) for fewer than 5 pairs, zero x variance, non-finite
   coefficients, or non-positive slope (L324-367).
7. **Cells apply (stage 8)** — `pipelines/build_adjusted_fixture_sections.py:284-298`
   `adjusted = max(0, alpha + beta * raw_val)`, then `_rescale_exact`
   (L43-69) snaps the per-position adjusted total to the raw combo's pie
   target (`index_total[pos].target_total`, L305-321) for the per-position
   "new pie" method, then to a global target when the legacy
   `index_total.global.target_total` exists (L327-333).

### Standing constraints already encoded in this stack

- **Canonical identity** — all names resolve through `canonical_players.Registry`
  keyed by `player_key` (JEG-75 standing rule 2026-10-02; `unified.py:44`,
  `vorp_via_roster.py:38`). Fail-closed on unresolvable identity (`unified.py:204-209`).
- **Freshness = content vintage, not pull time** — `app/trade-value-chart`
  reads `content_vintage`; the lineage monitor stamps `live_scraped_at`
  but does not let pull time override content vintage
  (`source-value-lineage.json:2-3`, `live_scraped_at` field distinct from
  `source_built_at`).
- **Methodology change must not shift existing published values without
  explicit Jeremy approval.** The lineage monitor's `ddf_rebuilt` field
  (`source-value-lineage.json:`, e.g. the JSN row at L4725 shows
  `ddf_rebuilt: 40.0` matching the pre-change published chart_value) is the
  cross-check: a successful methodology fix should not move `ddf_rebuilt`
  for the four as-published adjusted legs without a separate sign-off.
- **DDF-native exemption** — espn / cbsros / razzball are DDF-native
  (`build_adjustment_inputs.py:100`); their `identity` fit already
  activates the widget's live refit path. They are **out of scope** here.

### Spot-check evidence (current build, half-PPR 12-team, `fantasycalc_adjusted`)

`dist/modules/source-value-lineage.json:4511-4725`, key rows:

| player          | rank | native   | waiver | implied_vorp | indexed | chart_value | ddf_rebuilt |
| --------------- | ---- | -------- | ------ | ------------ | ------- | ----------- | ----------- |
| jahmyr gibbs    | 1    | 10819.0  | 134.0  | 10685.0      | 70.0    | 71.9        | 71.9        |
| bijan robinson  | 2    | 10143.0  | 134.0  | 10009.0      | 65.6    | 68.1        | 68.1        |
| chase brown     | 6    | 6758.0   | 134.0  | 6624.0       | 42.7    | 42.1        | 42.1        |
| jaxon smithnjigba (FC) | 10 | 9914.0 | 16.0   | 9898.0       | 55.0    | 40.0        | 40.0        |
| jaxon smithnjigba (FP) | 16 | 50.0  | 5.0    | 45.0         | 44.83   | 32.3        | 32.3        |

(`chase brown` row at `source-value-lineage.json:4630` (rank 6); other rows
interpolated from the contiguous top-25 listing at L4511-4725.)
The 9898 vs 10685 vs 45 numbers all carry their source's own positional
economy. The cells in stage 2 / stage 8 cannot unscramble that.

### Walkthrough doc

The walkthrough Google Doc describes **CURRENT** behavior (subtract-then-strip).
It must be revised **after** the methodology call lands, not as part of this
build — that is a follow-up ticket, not in scope for the code change.

## 3. Scope

### In scope

- Stage ordering inside `pipelines/vorp_translation/unified.py::translate_source`
  (L149-266) and any helper it calls, so waiver subtraction happens inside one
  consistent economic system.
- Per-(position, role) translation/fitting code that sits between native load
  and waiver subtraction (new stage; nothing in current code lives there).
- The lineage monitor's per-row `implied_vorp`, `vorp_replacement_level`,
  `vorp_inferred_position`, `vorp_inferred_n_rostered`, and `ddf_rebuilt`
  fields must continue to populate for the four as-published adjusted legs
  (`fantasycalc_adjusted`, `usatoday_adjusted`, `fantasypros_adjusted`, `cbs_adjusted`).
- A new regression test pinning the new stage order so any future reordering
  that puts subtraction back on raw publisher rows fails CI.
- Per-position pie invariant (sum of `adjusted` per position equals the raw
  combo's pie target within rounding) must still hold for the four adjusted
  legs.

### Explicitly out of scope (do not change in this ticket)

- **OUR_MAX anchors** in `unified.py:59-64` (`{QB 25, RB 70, WR 55, TE 30}`).
  Anchoring to our scale is correct; this ticket fixes *when* we map, not
  *where we map to*.
- **The DDF two-tier leg itself** (`pipelines/build_ddf_two_tier_leg.py` and
  its artifacts). It already produces a coherent value-above-waivers curve
  with our own roster settings; this ticket consumes it, does not touch it.
- **Roster math** in `pipelines/vorp_translation/vorp_via_roster.py`
  (`apportion`, `allocate_flex_vorp_weighted`, `bench_for_teams`,
  `rostered_for_teams`, `roster_waiver_line`). The waiver-line **computation**
  uses this; that is correct. The bug is that this waiver line is being
  subtracted from a list still carrying publisher economics.
- **The DDF-native exemption** for espn / cbsros / razzball
  (`build_adjustment_inputs.py:100`). Those sources are already a coherent
  economic system and their identity fit is correct.
- **The walkthrough Google Doc.** It will need a follow-up revision after the
  methodology call lands. Logging the doc as needing revision belongs in this
  brief; the actual edit does not.
- **Existing published values.** Per standing rule, a methodology change must
  not shift published values without explicit Jeremy approval. Any delta in
  `chart_value` per player for the four adjusted legs is itself an output of
  this work and must be surfaced to Jeremy before promotion; the brief names
  the spot-check players (JSN, Gibbs, Chase Brown) so the delta is reviewable.

## 4. Acceptance criteria

Each criterion below is runnable. Numbered for reference.

1. **New stage order pinned by a regression test that FAILS if subtraction
   runs on raw publisher rows.** Add `tests/test_jeg180_stage_order.py` (or
   equivalent) that monkeypatches `translate_source` to assert that the value
   passed to subtraction has already been through the new translation /
   normalization stage. A negative-control patch that reverts the new stage
   (subtract directly on raw natives) must make this test FAIL. This is the
   regression-guard rule from AGENTS.md: a guard that does not prove it
   catches the bug it names is worse than no guard.
2. **All four adjusted legs (usatoday, fantasypros, fantasycalc, cbs)
   rebuild green.** Running the rebuild path on the built `dist/` (per
   `docs/AGENTS.md` trade-value-chart change protocol — 12-combo headless
   sweep, 3 scorings × 4 league sizes, against `dist/`) must produce
   `usatoday_adjusted`, `fantasypros_adjusted`, `fantasycalc_adjusted`,
   `cbs_adjusted` with non-empty `combos` and a populated `index_total`,
   with the lineage monitor marking each `live_scraped` row consistent
   (no `error` field, `chart_value` populated).
3. **Per-position pie invariant still holds.** For each of the four adjusted
   legs, the sum of `adjusted[slug]` over slugs in position `p` (after the
   stage-8 `_rescale_exact`) must equal `(index_total[p] or
   index_total.global).target_total` within 0.05 (one-cent rounding). Assert
   this for every populated (scoring, teams) combo.
4. **Lineage monitor top-25 deltas vs the old build are explainable per
   player.** For the spot-check players (Jaxon Smith-Njigba on both FC and
   FP paths, Jahmyr Gibbs on FC, Chase Brown on FC — see `source-value-lineage.json:4511-4725`,
   `:5330-5395` for FP), the per-row `chart_value` delta vs the pre-change
   build must be a function of the new stage ordering and must not move
   `ddf_rebuilt` unless Jeremy has signed off on the delta. The brief
   recommends producing a one-page delta sheet (rows × position × scoring
   × teams) before promotion; the deliverable is a CSV, not a code change.
5. **No change to OUR_MAX, the DDF leg, roster math, the DNF-native exemption,
   or the four upstream `*` (non-adjusted) sections.** `git diff --stat`
   after the build must show no edits to `pipelines/build_ddf_two_tier_leg.py`,
   `vorp_via_roster.py::{apportion, allocate_flex_vorp_weighted, bench_for_teams,
   rostered_for_teams}`, `unified.py:59-64` (OUR_MAX block), or the
   non-adjusted `fantasycalc` / `usatoday` / `fantasypros` / `cbs` source
   sections in `data/fixtures/current/comparison-sources-data.json`.
6. **`make validate` green.** All pre-existing tests
   (`tests/test_vorp_translation_unified.py`,
   `tests/test_translate_via_vorp.py`,
   `tests/test_adjustment_inputs.py`,
   `tests/test_adjusted_fixture_sections.py`,
   `tests/test_ddf_two_tier_leg.py`, etc.) must continue to pass.
7. **Walkthrough doc logged as needing revision.** A row is added to
   `docs/claude-log.md` (per AGENTS.md: any session that changes anything
   appends an entry) noting that the walkthrough Google Doc describes
   subtract-then-strip CURRENT behavior and must be updated after Jeremy's
   methodology call lands. The actual doc edit is a follow-up, not part of
   this build.

## 5. Relevant files

Repo paths (with line refs to what I actually read):

- `pipelines/vorp_translation/unified.py` — `translate_source` L149-266 (the
  subtraction site L237-243 is the contamination); `build_write_rows` L292-352;
  OUR_MAX L59-64.
- `pipelines/vorp_translation/vorp_via_roster.py` — `apportion` L78-95;
  `allocate_flex_vorp_weighted` L98-163; `rostered_for_teams` L189-254;
  `roster_waiver_line` L257-274; `compute_vorp_via_roster` L277-353.
- `pipelines/build_adjustment_inputs.py` — `fit_cells` L303-375 (identity
  fallback paths L324-367); `find_leg` L146-199 (DDF leg selection);
  `DDF_NATIVE_SOURCES` L100; `load_canonical` L202-221.
- `pipelines/build_adjusted_fixture_sections.py` — `role_map_for_teams`
  L88-130; cell apply L284-298; `_rescale_exact` L43-69; per-position pie
  rescale L305-321; global pie rescale L327-333; `ADJUSTED_SOURCES` L147
  (and the cbsros exemption note L148-151).
- `pipelines/build_ddf_two_tier_leg.py` — consumed by stage 2; referenced
  for `POSITIONS`, `REF_SLOTS`, `REF_FLEX_COUNT`, `REF_FLEX_ELIGIBLE`,
  `BENCH_MIX_12` from `unified.py:31-37` and `vorp_via_roster.py:30-35`.
  Out of scope to edit; in scope to read.
- `dist/modules/source-value-lineage.json` — current monitor output; the
  spot-check rows at L4511-4725 (fantasycalc_adjusted) and L5330-5395
  (fantasypros_adjusted). Per-row schema: `rank`, `player_key`,
  `live_value`, `native`, `indexed`, `reweighted`, `implied_vorp`,
  `vorp_replacement_level`, `vorp_inferred_position`,
  `vorp_inferred_n_rostered`, `ddf_rebuilt`. These fields must continue
  to populate post-change.
- `data/fixtures/current/comparison-sources-data.json` — the four
  non-adjusted source sections are read but not edited (criterion 5).
- `app/trade-value-chart/assets/adjustment-inputs.json` — stage 2 live
  asset; reads and writes must continue.
- `data/adjustment-inputs/<bake_id>/` — versioned stage-2 copies; must
  continue to be written.
- `tests/test_vorp_translation_unified.py`,
  `tests/test_translate_via_vorp.py`,
  `tests/test_adjustment_inputs.py`,
  `tests/test_adjusted_fixture_sections.py`,
  `tests/test_ddf_two_tier_leg.py`,
  `tests/test_lineage_vorp_roundtrip.py` — pre-existing tests that must
  still pass under criterion 6.
- `docs/AGENTS.md` — operating model (delegation + validation rule for
  trade-value-chart changes); the regression-guard rule cited in
  acceptance criterion 1.
- `docs/methodology.md` — referenced from
  `build_adjusted_fixture_sections.py:151` for the DDF-native exemption.
- `docs/claude-log.md` — to receive an entry under criterion 7.
- `docs/risk-register.md` — to receive a row if, after build, the new
  stage order exposes a durable correctness defect, stale doc, or
  missing validation path that future sessions would otherwise rediscover.

## 6. Test plan

### New tests (added by this ticket)

- `tests/test_jeg180_stage_order.py` — pins the new stage order. Must:
  - Mock `translate_source` to assert subtraction happens **after** the
    new translation/normalization stage and **on values that already
    carry DDF-space economics** (whatever shape option A or B produces).
  - Include a **negative-control** assertion: with a reversion patch that
    re-runs subtraction on raw publisher natives, this test fails. This
    satisfies the AGENTS.md regression-guard rule.
- `tests/test_jeg180_pie_invariant.py` — for each of
  `usatoday_adjusted`, `fantasypros_adjusted`, `fantasycalc_adjusted`,
  `cbs_adjusted`, for every populated (scoring, teams) combo, the per-position
  sum of `adjusted` matches `index_total[p].target_total` within 0.05.
  Mirrors `_rescale_exact`'s rounding tolerance
  (`build_adjusted_fixture_sections.py:64`).
- `tests/test_jeg180_lineage_continuity.py` — for the four adjusted legs,
  every row in the lineage monitor's `top25` has populated
  `implied_vorp`, `vorp_replacement_level`, `vorp_inferred_position`,
  `vorp_inferred_n_rostered`, `ddf_rebuilt`; no `error` field.
- `tests/test_jeg180_no_dnf_native_change.py` — assert that the
  `fantasycalc` / `usatoday` / `fantasypros` / `cbs` (non-adjusted)
  source sections in `data/fixtures/current/comparison-sources-data.json`
  are unchanged byte-for-byte (criterion 5).

### Existing tests that must still pass (`make validate`)

- `tests/test_vorp_translation_unified.py` — JEG-62 VORP translation unit tests.
- `tests/test_translate_via_vorp.py` — translate_via_vorp integration tests.
- `tests/test_adjustment_inputs.py` — stage-2 fit (cells, fallback rules).
- `tests/test_adjusted_fixture_sections.py` — stage-8 fixture section build.
- `tests/test_ddf_two_tier_leg.py` — DDF two-tier leg construction.
- `tests/test_lineage_vorp_roundtrip.py` — VORP round-trip lineage.
- `tests/test_quantile_mapping.py` — DDF-native quantile mapping (unchanged
  code path; sanity check).
- `tests/test_methodology_consistency.py`, `tests/test_methodology_payload.py`
  — methodology document vs. code consistency.
- `tests/test_scale_agreement.py`, `tests/test_anchor_scale_guard.py` —
  per-position scale agreement (acceptable end-to-end).

### Validation commands

- `make naming` — naming-guard invariant.
- `make reference` — reference artifact freshness.
- `make sync` — sync to `app/` and `dist/`.
- `make test` — full regression suite.
- `make validate` — the canonical gate; equivalent to
  `naming + reference + sync + test` per the Makefile.

Per the trade-value-chart change protocol in AGENTS.md, also run the
**12-combo headless sweep** (3 scorings × 4 league sizes) against the built
`dist/` and check `fixedPieIndexed` and `sourceScaleAgreement` in
`TradeValueCurveDiagnostics` for each combo. **Pie totals agreeing across
sources proves nothing about curve shape.** Spot-check the JSN, Gibbs,
Chase Brown rows in the rebuilt lineage monitor and explain the delta in
the review packet — do not promote if the delta is not explainable per
player.

## 7. Constraints

The worker is bound by these — not as a wishlist, as a blocklist:

- **No credentials.** Do not read, write, or print any `.env*`,
  `service_account.json`, Supabase keys, GitHub tokens, or `~/.config`
  secrets. The repo's `.gitignore` keeps `data/raw/` (33MB, gitignored,
  the only copy of the player-news pipeline's inputs); do not touch it.
- **No browser.** No Chrome / Chromium / Playwright / Puppeteer / headless
  fetching in this build. This is a pipeline-stage reordering, not a
  scrape. The walkthrough Google Doc describes current behavior; a
  follow-up ticket, not this one.
- **No vision / OCR.** No `mcode-tools` multimodal calls against any image,
  PDF, or screenshot. This brief cites the JSON monitor output only.
- **No Mac-only files.** No `.DS_Store`, no platform-specific paths. The
  worker is on Linux; do not introduce Mac-only artifacts even though the
  user's machine is Mac.
- **No merge, no push, no deploy.** Per AGENTS.md, this commit is on the
  branch `minimax/jeg-180-brief`. Do not `git push`, do not open a PR, do
  not run `make sync`, do not trigger GitHub Actions, do not promote to
  `main`, do not deploy to GitHub Pages. The user's standing constraint:
  "the user no longer needs to say the exact word Push or Publish." That
  rule applies when the work passes validation and is the documented
  publish path; this work is draft-only and not validated. Stop short.
- **No `~/Projects/"fantasy tools"` access.** The gitignored `data/raw/`
  lives there; this worktree does not need it.
- **Methodology decision is Jeremy's.** Do not write code that picks
  option A, B, or a third option. The brief presents options neutrally
  with evidence (below), gives a clearly-labeled RECOMMENDATION (also
  below), and explicitly marks the decision as **PENDING-JEREMY**. Any
  implementation PR must cite Jeremy's sign-off in its commit message.
- **No Linear access in this environment.** Do not try to create, update,
  or comment on a Linear ticket from here. This brief lives in the repo
  and is the handoff to the implementer.

---

## Methodology options (presentation, no decision)

Per the parent ticket's instruction: present the options neutrally with
evidence, label a RECOMMENDATION, mark the decision PENDING-JEREMY.

### Option A — translate first, subtract second

**Sequence:** raw natives → per `(position, role)` publisher→DDF map (fit on
the RAW natives per position/role against the DDF two-tier leg) → apply the
map → compute the waiver line from the DDF leg's own roster math, in DDF
space → subtract. Subsequent `OUR_MAX` and pie reindex are unchanged.

**Evidence it addresses the contamination:**
- The mapped values carry DDF-space positional economics before subtraction,
  so the implied "VORP" is a VORP in our system.
- The waiver line is computed from the DDF leg's roster (`dedicated + flex +
  bench` per `vorp_via_roster.py:251`), not from the publisher's own roster.
- The existing stage-2 cell fit and stage-8 pie rescale can be reduced to a
  near-identity correction on top of a coherent value, instead of being asked
  to unscramble non-linear shape distortion.

**Tradeoffs to flag for him:**
- The fit on RAW natives reuses stage-2's role assignment logic
  (`build_adjustment_inputs.py:260-300`), which is per-source — same role
  model, so no extra risk there.
- Cells become mostly identity for trade-chart sources (similar to the
  DDF-native exemption in `build_adjustment_inputs.py:413-419`). Some
  intentional cell slack is still useful for the residual scaling, so
  identity fallback should remain, not a hard-coded 1.0.
- The lineage monitor's `vorp_inferred_position` and `vorp_inferred_n_rostered`
  fields still need to populate for the monitor's downstream consumers
  (the dashboard's curve inspection); the build must stamp these from
  the DDF-side roster math, not from the publisher's.

### Option B — strip publisher economics first

**Sequence:** raw natives → per `(position, role)`, quantile / isotonic
normalize the publisher distribution onto the DDF leg group distribution
  (handles non-linear shape, not just linear tilt) → waiver subtraction,
  `OUR_MAX`, pie rescale as today.

**Evidence it addresses the contamination:**
- Quantile / isotonic mapping preserves rank order inside each position and
  pulls the distribution shape toward the DDF leg's shape, so the
  subtraction happens on values whose scale and shape match DDF's.
- Stage-2 cell fit (OLS affine) is largely redundant after quantile
  normalization and is expected to collapse to identity fallback
  (`build_adjustment_inputs.py:324-367`) for most `(position, role)` cells.

**Tradeoffs to flag for him:**
- Quantile / isotonic mapping introduces per-(position, role) interpolation
  that does not currently exist in the repo. It is a new piece of math that
  needs its own review and its own guard test (the AGENTS.md rule applies).
- `fantasypros` publishes no native for many reference players
  (`build_adjustment_inputs.py:236-237` skip rule); quantile normalization
  needs explicit handling for sparse overlap, or the new stage will quietly
  drop players the existing cell fit preserves.
- Two distinct sources can land on topologically different rank orderings
  for the same position; isotonic is monotone so this is preserved, but
  the resulting per-position distribution can still differ from DDF in
  ways quantile normalization cannot close (e.g., a publisher that ranks
  only 30 RBs vs. DDF's 100+). Out-of-range players need an explicit rule,
  not a fallback.

### RECOMMENDATION

**Option A** (translate first, subtract second) is recommended.

Why:
- It reuses the existing role-model + OLS-fit machinery (`build_adjustment_inputs.py`)
  and the existing roster math (`vorp_via_roster.py`). The new code is a stage
  inserted *before* subtraction, not a new fit family.
- It produces a coherent intermediate (mapped values in DDF space) that is
  directly auditable from the existing lineage monitor with a small field
  rename (`implied_vorp` becomes `mapped_then_vorp` or similar — to be
  decided by Jeremy alongside the methodology call).
- It does not require introducing quantile / isotonic math into a
  correctness-sensitive path that has been running without it.
- The lineage monitor spot-check (JSN row at `source-value-lineage.json:4725`:
  native 9914 → implied_vorp 9898 → chart_value 40) becomes explainable as
  "implied_vorp was contaminated by FantasyCalc's WR-positional economy; the
  mapped-then-vorp value is the correct number for the chart" — a single
  sentence, with the mapped value pinned in the row.

The downside of A vs B is that A still relies on an affine fit per
`(position, role)` and so is bounded by what a straight-line map can express;
B's quantile / isotonic does better at closing non-linear shape distortion
(per the parent issue's note that "quantile/isotonic handles non-linear
shape, not just linear tilt"). This is the actual methodological trade-off
Jeremy must call.

### Decision

**PENDING-JEREMY.** This brief does not pick A or B; the implementer
must not start the code change until the parent ticket records Jeremy's
choice (or a third option) in writing.

---

## Handoff log (per AGENTS.md: log what you did before you finish)

Drafted 2026-10-02 by minimax (M3). Read: `pipelines/vorp_translation/unified.py`
(translate_source L149-266, build_write_rows L292-352, OUR_MAX L59-64);
`pipelines/vorp_translation/vorp_via_roster.py` (full file, with attention
to apportion L78-95, allocate_flex_vorp_weighted L98-163,
rostered_for_teams L189-254, roster_waiver_line L257-274,
compute_vorp_via_roster L277-353); `pipelines/build_adjustment_inputs.py`
(fit_cells L303-375, DDF_NATIVE_SOURCES L100, load_canonical L202-221);
`pipelines/build_adjusted_fixture_sections.py` (cell apply L284-298,
_rescale_exact L43-69, pie rescale L305-333, ADJUSTED_SOURCES L147);
`dist/modules/source-value-lineage.json` (spot-check rows at L4511-4725
and L5330-5395). Did NOT read: `pipelines/build_ddf_two_tier_leg.py`
(out of scope, no edit planned); `docs/methodology.md` (referenced via
`build_adjusted_fixture_sections.py:151`); the walkthrough Google Doc
(parent ticket confirms it describes CURRENT behavior and is a follow-up).

**Verified:** line refs above were read in this session. **Claimed without
confirming in this session:** the cross-row totals and per-row player_key
spot-checks (Gibbs rank 1, JSN rank 10 FC, JSN rank 16 FP, Chase Brown
rank 6) were interpolated from the contiguous `top25` listing and may need
a re-grep against the live file when implementation begins.

**Unverified:** the JSN defect lineage (AGENTS.md mentions a 2026-09-30
`native_value` drop in `match_source_snapshot.py` that flattened 9914 → 50.7);
that is upstream of this ticket and is mentioned only as evidence the
native-value path is fragile to reordering. Any 2026-09-30 staging bug
in match_source_snapshot is fixed; this ticket does not re-open it.

**Did not run:** `make validate` (the brief is draft-only; no code changed;
no test was run). The implementer runs `make validate` after Jeremy's
methodology call lands and the code change is made.