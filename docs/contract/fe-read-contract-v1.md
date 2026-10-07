# JEG-327 — FE Read Contract v1

**Ticket:** JEG-327 — Define FE/BE boundary and versioned frontend read contract
**Phase:** B — contract draft (Phase A inventory complete)
**Lane:** minimax (M3)
**Date:** 2026-10-04
**Status:** DRAFT — contract definition + sequencing only; no DDL applied, no migration built
**Phase A inventory:** `docs/contract/fe-dependency-inventory.md` (also
`lanes/inbox/chatgpt/JEG-327-inventory.md` in main checkout)
**Phase A verification report:** §10 below

> **Non-goal (verbatim from brief):** "Mixing FE/BE separation with unrelated
> methodology changes." This contract defines surfaces, fields, ownership
> boundaries, and sequencing. It does not change values, rescale pies, alter
> the VORP translation, or modify user-facing copy. Every methodology-adjacent
> decision flagged in §11 below returns to the JEG-327 ticket for Jeremy.

---

## 1. Scope and constraints (from the brief)

### 1.1 What the contract is

A **versioned, frontend-facing read surface owned by Supabase** (recommended
`api` schema), projected from `public.consolidated_values` and the other
backend sources. The FE talks to **exactly one module** — `product-data.js` —
which talks to this contract. Nothing inside `app/trade-value-chart/` reads
anything outside `product-data.js`.

### 1.2 What the contract is NOT

- It is **not** a methodology change. `value-model.js` pure functions remain
  pure, `TwoTier` browser economics keep their invariants, and the pipeline
  (`pipelines/`) is not edited by Phase B.
- It is **not** a guarantee that the JEG-329 on-demand VORP view exists.
  JEG-329/332/333/334 are parked (JEG-331 verdict: the precondition failed).
  Superseded 2026-10-06 by `docs/decisions.md` league-settings-001: the
  backend saves one setup (12 teams, standard roster) per scoring format and
  the browser derives team count, roster shape and bench share.
  The contract must represent the **present** view coverage honestly and
  reserve **versioned extension points** for the VORP-family rework.
- It is **not** a deploy. No DDL is applied. The SQL in
  `sql/contract/api_v1.sql` is a draft for review and Roman's integration;
  Roman applies it through the Supabase SQL editor and runs
  `NOTIFY pgrst, 'reload schema'`.

### 1.3 Ground truth the contract must respect (2026-10-04)

Per the JEG-331 evidence on live `public.consolidated_values`:
- `vorp`: 635 rows, **all full-PPR / 12-teams**.
- `vorp_indexed`: 624 rows, **all full-PPR / 12-teams**.
- `adj_values`: 635 rows, **all full-PPR / 12-teams**.
- `combo_reindexed`: full coverage across all 12 (scoring × teams) combos.

The contract represents this honestly: per-view coverage dimensions with
explicit "not available for this combo" semantics, never silent absence.

### 1.4 Direction the contract must implement (2026-10-03, Jeremy-approved)

> Strip browser-side economics to bake time. "Server side" here means the
> bake pipeline, not a live API (the chart is static GitHub Pages): move
> computation into the pipeline and ship precomputed values in the artifacts.

> Bench-share slider: vector+blend. The pipeline solves the two-tier
> calibration once per combo and ships per-position tier price vectors
> (starter-tier price, bench-tier price); the browser computes each player's
> value as a linear blend weighted by the slider's share.

> Parity requirement: vector+blend must land at the same results as the live
> solve. Phase E acceptance gate = a parity test comparing blend vs the
> current browser solve across the full slider range for every combo; pass =
> exact or sub-display-unit agreement (values render to one decimal).

The contract carries the precomputed slices. Tier price vectors per position
per combo live in `api.player_values` (justified in §3.1.3).

### 1.5 Combo matrix bound

The current shipped artifact is `comparison-sources-data.json` at 2.7MB. To
avoid ballooning past today's budget, the combo matrix is bounded to:

| axis | values |
|---|---|
| scoring | full, half, standard (3) |
| teams | 8, 10, 12, 14 (4 — matches the consolidated_values CHECK) |
| qb_variant | qb1, qb2, none (3) |
| roster_shape | 4 named shapes (default 1QB, default SUPERFLEX, custom-A, custom-B) |
| view | combo_reindexed (full coverage); vorp, vorp_indexed, adj_values (full-PPR/12-teams only) |
| source | 14 keys verbatim from `SOURCE_KEYS` |

This is 3 × 4 × 3 = 36 combo keys (the brief says "12-combo headless sweep"
for 3 × 4 — `qb_variant` collapses to `none` for non-fantasycalc and to
`qb1`/`qb2` only for fantasycalc). Tier price vectors are 4 positions × 2
tiers = 8 per combo. Pre-baked artifact budget: ≤ 3.0MB.

---

## 2. Surface set: the five semantic surfaces

The contract ships **exactly five** semantic surfaces. The inventory
identified 11 distinct frontend read paths (8 JSON artifacts + 3 inline
islands); collapsing them to five surfaces is the contract's job, not the
FE's. Each surface has one owner (Supabase), one grain, and one
`contract_version` (semver-style, MAJOR.MINOR.PATCH — see §7).

| # | surface | grain (logical) | backing today | row count bound (today) |
|---|---|---|---|---|
| 1 | `api.player_values` | (player, source, season, week, scoring, teams, qb_variant, view) | `public.consolidated_values` (8-col PK) | ~20k rows, growing weekly |
| 2 | `api.players` | player_key (number) | `public.players` (canonical identity) | current 610 |
| 3 | `api.player_context` | (player_key) with arrays of news/adjustments | `public.player_news`, `public.player_adjustments` (new) | current 610 players, ~544 with news |
| 4 | `api.product_options` | product_key="default" (singleton, app-config-shaped) | derived from `public.product_options` (new singleton table) + `api.product_snapshot` | 1 row |
| 5 | `api.product_snapshot` | snapshot_id (single active row, history kept) | `public.product_snapshot` (new) + `public.source_trade_values` aggregates | 1 active + history |

**Justification for NOT going smaller:** every one of the five has a distinct
grain, a distinct ownership boundary (data vs metadata vs selector vs
identity vs context), and a distinct failure mode. Merging any two would
either widen an RLS surface or force the FE to filter server-side results
that the FE should not be filtering. The inventory's "5 surfaces" proposal
is preserved.

**Justification for NOT going larger:** the inventory lists 11 paths but
they collapse cleanly. The 3 inline islands (`players-data`,
`methodology-data`, no inline `sources-data`) become rows of `api.players`,
`api.product_options`, and `api.player_values` respectively. The 3 CSS
files and the Google Fonts CSS are external styling, not data. The 4 RSS
feeds are dead metadata (inventory §1.3); they do not enter the contract.

---

## 3. Surface specifications

### 3.1 `api.player_values`

The single surface for every value the chart renders. Per-row VALUE
PROVENANCE and per-view COVERAGE METADATA live here, not in
`api.product_snapshot`, because the FE's honesty layer renders them next to
the value.

#### 3.1.1 Grain

`(player_key, source, season, week, scoring, teams, qb_variant, view)`

One row per logical cell. Backed by `public.consolidated_values` (8-col PK,
4 views: `combo_reindexed`, `vorp_indexed`, `vorp`, `adj_values`). The
`view` dimension is the only column that varies view semantics; the others
identify the bake cell.

#### 3.1.2 Fields

| field | type | nullable | description |
|---|---|---|---|
| `player_key` | `bigint` | no | Canonical identity; same int used by `api.players.player_key`. |
| `source` | `text` | no | Source key verbatim (11 keys: `fantasycalc_adjusted`, `cbsros`, …). |
| `season` | `int` | no | e.g. 2026 |
| `week` | `int` | no | 1–18 |
| `scoring` | `text` | no | CHECK in {'full','half','standard'} |
| `teams` | `int` | no | CHECK in {8,10,12,14} |
| `qb_variant` | `text` | no | CHECK in {'qb1','qb2','none'} — `none` except fantasycalc* family |
| `view` | `text` | no | CHECK in {'combo_reindexed','vorp_indexed','vorp','adj_values'} |
| `value` | `numeric` | no | Exact as computed; never rounded in storage (rounding is presentation). |
| `value_provenance` | `text` | no | One of `'native'`, `'ddf_translated'`, `'indexed'`, `'vorp'`, `'adj'`. See §3.1.4. |
| `model_vs_published` | `text` | no | One of `'model'` (DDF-translated, e.g. ESPN), `'published'` (publisher's own chart). See §3.1.5. |
| `detail_locator` | `text` | no | Deterministic path in the bake detail fixture, e.g. `sources.fantasycalc_adjusted.combos.full_12_qb1.reindexed['josh allen']`. Carried from `public.consolidated_values.detail_locator`. |
| `bake_id` | `text` | no | Which bake produced this row. From `public.consolidated_values.bake_id`. |
| `index_total` | `numeric` | yes | Per-position pie target for this combo (the shared-set anchor total). NULL when the view does not emit a pie. |
| `pie_vintage` | `text` | yes | The pie's own `bake_id` (per source) — used by the publish gate to reject indexed values pinned to a pie older than their inputs. See §6.1. |
| `tier_price_vector` | `jsonb` | yes | Only on `view='combo_reindexed'` rows where the source has a baked two-tier calibration. Shape: `{"QB":{"starter":<num>,"bench":<num>,"rw":<num>,"rs":<num>,"tau":<num>}, …}`. NULL on pure-VORP/adj views and on as-published sources (FantasyCalc, USA Today, FantasyPros, CBS) that don't run two-tier. The browser uses this with `vector+blend` (§9.2). |
| `tier_price_vintage` | `text` | yes | The `bake_id` of the two-tier calibration this vector came from. MUST equal the `bake_id` of the same row's `value` — the publish gate refuses otherwise. |

#### 3.1.3 Justification: `tier_price_vector` in `api.player_values` (not `api.product_options`)

The brief allows either placement. The deciding factor: `api.product_options`
is **singleton and selector-shaped** (one row keyed on `product_key='default'`)
and carries per-user **knobs** (bench-share bounds, default scoring/teams).
Tier price vectors are per-(source, combo) baked data, identical in shape
to `value`. Putting them in `api.player_values` keeps every value the chart
renders in one place, lets the FE fetch a single row's vector alongside its
value (single index seek on `bake_id` + `view`), and avoids a second
surface that would have to be cross-joined at render time anyway.

The browser's `vector+blend` reads `tier_price_vector` from the same row
that holds `value`. They share `bake_id` and `tier_price_vintage`; the
publish gate verifies both.

#### 3.1.4 `value_provenance` enum (six values; not the four listed by the brief)

The brief lists "native vs DDF-translated vs indexed" — three categories.
The inventory's `comparison-sources-data.json` schema reveals a finer
taxonomy (the brief mentions "the model-vs-published taxonomy from the
definitions layer"):

| value | meaning | example rows |
|---|---|---|
| `native` | Publisher's own raw number, unchanged by any reindex/normalize | `fantasycalc.combos.full_12_qb1.native` |
| `indexed` | Proportionally scaled onto the anchor's pie (as-published sources) | `fantasycalc_adjusted.combos.full_12_qb1.reindexed` |
| `ddf_translated` | DDF two-tier leg output (ESPN, CBS ROS, Razzball) | `espn.combos.full_12.combo_reindexed` |
| `vorp` | Raw value-above-waivers, browser-computed pre-Phase E; baked post-Phase E | `espn.combos.full_12.vorp` |
| `vorp_indexed` | `vorp` after proportional scaling onto the anchor's pie | `fantasycalc.combos.full_12.vorp_indexed` |
| `adj` | Adjusted-values view (JEG-242's third view mode) | `fantasycalc.combos.full_12.adj_values` |

#### 3.1.5 `model_vs_published` enum

The honest two-bucket split the definitions layer already uses:

| value | meaning | which sources |
|---|---|---|
| `model` | DDF-translated; the values are a model output, not a publisher's published chart | ESPN, CBS ROS, Razzball |
| `published` | The values are the publisher's own published chart (possibly reindexed onto the anchor pie, but the ranking came from the publisher) | FantasyCalc, USA Today, FantasyPros, CBS, and their `_adjusted` siblings |

Every row has exactly one `value_provenance` and exactly one `model_vs_published`.
The two are independent: a `published` row can have `value_provenance='vorp'`
(FantasyCalc's vorp_indexed is a published source's vorp view, scaled).

#### 3.1.6 Per-view coverage metadata

The contract must represent the JEG-331 ground truth honestly. Per-view
coverage is a **per-view, per-combo** decision:

| view | scoring × teams × qb_variant served today | source-set served today |
|---|---|---|
| `combo_reindexed` | all 36 combos (3 scoring × 4 teams × 3 qb) | all 14 source keys (as-published sources restricted to `qb_variant='none'`; fantasycalc* restricted to `qb_variant='qb1'` or `'qb2'`) |
| `vorp` | full-PPR × 12-teams × qb1 only (per JEG-331: 635 rows, all full-PPR/12-teams) | ESPN, CBS ROS, Razzball (the three pure VORP keys) |
| `vorp_indexed` | full-PPR × 12-teams × qb1 only (per JEG-331: 624 rows) | FantasyCalc, USA Today, FantasyPros, CBS |
| `adj_values` | full-PPR × 12-teams × qb1 only (per JEG-331: 635 rows) | as-published sources that emit `adj_values` (all four) |

The FE must NEVER silently miss rows. The contract provides a per-row
`coverage_class` that the FE can render:

| `coverage_class` | meaning | FE behavior |
|---|---|---|
| `full` | view + combo + source are all available | render the value |
| `view_limited_combo` | view exists but not for this (scoring × teams × qb_variant) | render "—" with a tooltip "vorp views are not available for half-PPR × 14-teams" (the brief: explicit "not available for this combo" semantics) |
| `view_limited_source` | view + combo exist but not for this source | render "—" with tooltip naming the source |
| `stale` | row exists but `pie_vintage < bake_id` (publish-gate violation rejected upstream; FE never sees this, but defensive render is "—" with red border) | refuse to render — fail-closed |

**NOT a contract surface:** the JEG-329 on-demand VORP view. The brief
mandates: "Do not design the contract as if the JEG-329 on-demand view
exists — version it as a future extension." The contract reserves
`view='vorp_on_demand'` as a future extension point in the CHECK constraint
if Jeremy approves JEG-329/332/333/334; the schema, backing table, and FE
behavior for it are intentionally undefined in v1.

#### 3.1.7 Ownership

- **Backend-owned:** `value`, `value_provenance`, `model_vs_published`,
  `index_total`, `tier_price_vector`, `tier_price_vintage`, `detail_locator`,
  `bake_id`, `pie_vintage`. Written by the bake pipeline only.
- **Supabase-computed (view):** the row assembly itself (projected from
  `public.consolidated_values` via `sql/contract/api_v1.sql::api.player_values`).
- **Frontend-readonly:** every field.

#### 3.1.8 Lineage

Every row carries `bake_id` (the bake that produced the value) and
`detail_locator` (the path in that bake's detail fixture). The publish
gate verifies `tier_price_vintage = bake_id` for rows where
`tier_price_vector IS NOT NULL`. The FE may render "Vegas" (publisher
+ week) from `api.product_snapshot.sources[source]` joined by `source` —
no `display` map duplicated here.

#### 3.1.9 Freshness semantics

Freshness = **content vintage**, never pull time. Each row's effective
freshness is `MAX(bake_id, pie_vintage, tier_price_vintage)` —
whichever is newest is what the value reflects. The FE compares that to
the same source's freshness in `api.product_snapshot` and renders
"stale (bake < pie)" if the row's bake lags its pie.

### 3.2 `api.players`

#### 3.2.1 Grain

`player_key` (one row per canonical player).

#### 3.2.2 Fields

| field | type | nullable | description |
|---|---|---|---|
| `player_key` | `bigint` | no | Canonical identity (PK). |
| `canonical_name` | `text` | no | Display name. The brief flags "full_name vs name" as an open question (§10 #9); v1 picks `canonical_name` and the FE drops the `full_name ‖ name ‖ ""` chain. |
| `pos` | `text` | no | One of {QB, RB, WR, TE, K, DST}. The chart renders only QB/RB/WR/TE; K/DST are in the surface because the inventory says they "are baked in the fixture" but "silently dropped by both widgets' position filters" — and the canonical naming table needs them representable. |
| `team` | `text` | yes | NFL abbrev. `"—"` substituted for teamless rows (the brief flags this as a soft spot; v1 keeps the substitution but renders it visibly as "FA"). |
| `ir_zeroed` | `bool` | no | TRUE for the 4 `espn_zeroed` player_key IDs that carry an IR badge; the FE renders the badge from this column instead of an `espn_zeroed[]` array on the snapshot. |
| `kdst_excluded_from_chart` | `bool` | no | TRUE for K/DST positions; the FE filters them at render. Computed data for them stays internal (they appear in the table for canonical-naming coverage but the chart never renders them). |
| `espn_ppg` | `jsonb` | yes | `{"ppr": <num>, "half_ppr": <num>, "standard": <num>}` — ESPN's per-game projections. |
| `rz_ppg` | `jsonb` | yes | Same shape; Razzball. |
| `cbsros_ppg` | `jsonb` | yes | Same shape; CBS ROS. |
| `ecr_ppg` | `jsonb` | yes | ECR leg's per-scoring PPG (for blending; pipeline decides what fills this). |
| `blend_ppg` | `jsonb` | yes | The pipeline-blended per-game projection per scoring. |
| `games_remaining` | `int` | yes | ROS games for this player (from blend). |

#### 3.2.3 Ownership

- **Backend-owned:** every field. Source: `public.players` (canonical naming
  table) + `public.espn_season_projections` + `public.razzball_projections`
  + `public.cbs_ros_projections` (joined on `player_key`).
- **Frontend-readonly.**

#### 3.2.4 Lineage

Every row's freshness is `MAX(snapshot_date)` across the contributing
projection tables. Surfaced via `api.product_snapshot.players_snapshot_at`.

#### 3.2.5 Freshness

Content vintage from each contributing snapshot. The FE never compares to
pull time.

### 3.3 `api.player_context`

#### 3.3.1 Grain

`player_key` (one row per player with non-empty news/adjustments). Players
with neither news nor adjustments are **omitted** (the FE handles missing
keys as "no news" — this matches the inventory's current behavior of empty
`news_by_player_key`).

#### 3.3.2 Fields

| field | type | nullable | description |
|---|---|---|---|
| `player_key` | `bigint` | no | Canonical identity. |
| `news` | `jsonb[]` | no | Array of `{title, summary, published_at, source, source_reliability, url, tags[]}` (verbatim from `player-news.json`). |
| `adjustments` | `jsonb[]` | no | Array of `{id, kind, weeks_out, weeks_out_range, date, status, injury, note, source, consumed, consumed_at, skip_form, beneficiary_review}` (verbatim from `player-news.json`). |
| `as_of` | `timestamptz` | no | Content vintage of this player's news/adjustments. |

#### 3.3.3 Ownership

- **Backend-owned.** Source: `public.player_news` (new table; mirrors
  `player-news.json`'s `news_by_player_key`), `public.player_adjustments`
  (new; mirrors `adjustments_by_player_key`), `public.player_review`
  (mirrors `checked_but_not_adjusted`).
- **Frontend-readonly.**

#### 3.3.4 Lineage

`as_of` is the latest `published_at` (news) or `date` (adjustments) for
the row. The `meta` block (`trade_values_published_at`,
`injury_data_updated_at`, etc.) is lifted into `api.product_snapshot`
(§3.5.4) — not duplicated here.

#### 3.3.5 Freshness

`as_of` per row. The meta timestamps go to `api.product_snapshot`.

### 3.4 `api.product_options`

#### 3.4.1 Grain

`product_key = 'default'` (singleton).

#### 3.4.2 Fields

| field | type | nullable | description |
|---|---|---|---|
| `product_key` | `text` | no | `'default'` (the singleton). |
| `contract_version` | `text` | no | Matches `api.product_snapshot.contract_version`. See §7. |
| `bench_share` | `jsonb` | no | `{"default": 0.15, "min": 0.01, "max": 0.30, "user_settable": true}`. The slider is **bounded** — the inventory's TwoTier browser validates feasibility at the active share and refuses outside the per-position feasible interval; v1 sets the global bound to the **intersection** of per-position bounds (today: `[0.01, 0.30]`), and per-position bounds ship via `api.player_values.tier_price_vector`'s `feasible_interval` extension (future). **JEG-432 R2 (2026-10-07):** `[0.01, 0.30]` is now the *product* range only. The active slider bounds and the per-position `feasible_interval` are computed in the browser per league by the rule `feasible-bench/1` (`ValueModel.feasibleBenchBounds`, Python reference `pipelines/feasible_bench_bounds.py`) from inputs already shipped (ESPN per-game projections + the two-tier reference pool), per league-settings-001 -- no stored row per setup. The same rule bounds the roster Bench stepper. See `fe-v3-backend-requirements.md` R2. |
| `bench_share_default` | `numeric` | no | `0.15`. Lifted out of `bench_share.default` for convenience. |
| `bench_share_min` | `numeric` | no | `0.01`. Same. |
| `bench_share_max` | `numeric` | no | `0.30`. Same. |
| `bench_share_user_settable` | `bool` | no | `true`. Same. |
| `default_scoring` | `text` | no | `'full'`. Canonical contract spelling is `'full'`/`'half'`/`'standard'` (matches `public.consolidated_values` and the comparison dashboard). The curve widget's internal keys differ (`'ppr'`/`'half_ppr'`/`'standard'` — `curve-widget.js:5`); `product-data.js` owns the mapping (`full`→`ppr`, `half`→`half_ppr`, `standard`→`standard`) and no other FE module may re-derive it. |
| `default_teams` | `int` | no | `12`. |
| `default_roster_shape` | `jsonb` | no | `{"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"BENCH":6}`. Matches `curve-widget.js` `DEFAULT_ROSTER` (K:0/DST:0 omitted per the JEG-211 honest exclusion — K/DST are off the chart). |
| `default_lock_order` | `text` | no | `'espn'`. |
| `default_view_mode` | `text` | no | `'indexed'` (the JEG-242 view mode). |
| `default_reference_source` | `text` | no | `'usatoday'` for the comparison dashboard; matches the code default (`comparison-dashboard.js:205`). |
| `default_position_weights` | `jsonb` | yes | `NULL` in v1 — the FE code defaults `positionWeights = null` and reads the fixture pies directly (`curve-widget.js:763,1719`); per-source pie shares live in `api.product_snapshot.methodology_combos.position_shares`. A non-null global override is a future MINOR extension. |
| `min_shared_for_pie` | `int` | no | `40`. The brief flags this as open question #2; v1 freezes it (the existing constant) and ships it as part of the contract so the FE doesn't re-define it. |
| `starter_markup_sane_band` | `jsonb` | no | `[0.98, 1.6]`. The brief's open question #3; v1 freezes it. |
| `peak_agreement_band` | `jsonb` | no | `[0.80, 1.25]`. Same. |
| `source_keys` | `text[]` | no | The 14 source keys verbatim. Drives `runRegressionGuards.sourceMapCoverage`. |
| `adjusted_indexed_keys` | `text[]` | no | `['fantasycalc_adjusted', 'usatoday_adjusted', 'fantasypros_adjusted', 'cbs_adjusted']`. Drives `adjustedCurvePaused`. |
| `pure_vorp_keys` | `text[]` | no | `['espn_vorp', 'cbsros_vorp', 'razzball_vorp']`. |
| `as_published_keys` | `text[]` | no | `['usatoday', 'fantasycalc', 'fantasypros', 'cbs']`. Drives the `singleScale: true` branch in `normalizeToFixedPie`. |

#### 3.4.3 Why the bench-share bounds/default live here

The brief mandates: "`api.product bench` must carry the bench-share
parameter bounds/default (default 0.15, user-settable, bounded) so the
knob is not hardcoded in FE." `bench_share_default` is also referenced by
`comparison-dashboard.js:23` (`DEFAULT_BENCH_SHARE = 0.15`),
`curve-widget.js:759` (`DEFAULT_BENCH_SHARE`), and the TwoTier module
(`DEFAULT_BENCH_SHARE_TT = 0.15`). v1 ships it in the contract so the FE
removes those constants.

#### 3.4.4 Ownership

- **Backend-owned.** The defaults are baked into a `public.product_options`
  table; the FE reads `api.product_options` and never the raw table.
- **Frontend-mutable at runtime:** `bench_share` (slider), `roster_shape`
  (form), `position_weights` (sliders), `lock_order` (radio), `view_mode`
  (tab). These are session-only; nothing persists to Supabase.

#### 3.4.5 Lineage

Tied to `api.product_snapshot.contract_version` (must match). Mismatch
→ fail-closed (the FE refuses to render — §7).

### 3.5 `api.product_snapshot`

The freshness/identity block. Carries everything that is not a value, a
player, or news — but that the FE needs to render correctly.

#### 3.5.1 Grain

`snapshot_id` (single active row, history retained; `is_active = true`
flags the current one).

#### 3.5.2 Fields

| field | type | nullable | description |
|---|---|---|---|
| `snapshot_id` | `uuid` | no | PK; the bake identity. |
| `contract_version` | `text` | no | The contract version this snapshot conforms to (see §7). |
| `built_at` | `timestamptz` | no | When this snapshot was assembled (NOT a freshness signal; content vintage is per-source). |
| `value_weeks` | `jsonb` | no | `{"ecr": <int>\|null, "espn": <int>\|null, "monday": <int>\|null, "pm": <int>\|null, "rz": <int>\|null}`. |
| `sources` | `jsonb` | no | Per-source metadata: `{name, kind, claimed_settings, position_coverage, native_unit, update_cadence, value_provenance, model_vs_published, week_designated, content_vintage, fetched_at, promoted_at, promoted_from_review, promotion_note, provenance_note, url, reindex_anchor, fit_bake_id, source_provenance, espn_snapshot, espn_status, espn_priced_pids, method, method_group, status}`. One entry per source key. |
| `source_validation` | `jsonb` | no | `{<source>: "live"\|"stale"}`. Drives `runRegressionGuards.sourceMapCoverage` (fail-closed: any missing key → throw). |
| `espn_zeroed` | `int[]` | no | The 4 `espn_zeroed` player_key IDs (mirrored from `data.espn_zeroed[]`; the badge actually lives on `api.players.ir_zeroed` per §3.2.2 — this array is a snapshot-level denormalization for cross-widget consistency). |
| `methodology_combos` | `jsonb` | no | The `methodology-data` island's payload verbatim (`default_combo`, `bench_share`, `combos[<key>]` with `position_shares`, `adjustments`; per-source `default_weights`). |
| `reference_freshness` | `jsonb` | no | Verbatim from `reference-freshness.json` (SHA-256 of the shipped artifacts, `enforced` flag). |
| `health` | `jsonb` | no | `{source_import_health, pipeline_cron_state, ...}` — the JEG-322 backend health view, once Phase C lands. Before Phase C: NULL (the FE's inline health script keeps reading `dist/modules/source-import-health.json` directly until Phase C ships). |
| `is_active` | `bool` | no | Exactly one row has `is_active=true`. |
| `pie_vintage_per_source` | `jsonb` | no | `{<source>: <pie_vintage_bake_id>}` — the publish gate uses this to reject indexed values pinned to a pie older than their inputs. See §6.1. |
| `players_snapshot_at` | `timestamptz` | no | The canonical players content vintage for this snapshot. |
| `context_meta` | `jsonb` | yes | The `meta` block from `player-news.json`: `trade_values_published_at`, `injury_data_updated_at`, `source_refresh_at`, `latest_actionable_news_at`, `feeds[]`, `fetched/raw/matched/...` counts. |

#### 3.5.3 Why methodology_combos lives here

The `methodology-data` island is **methodology copy** (the position shares
the user reads, the pie visualizations). It belongs to the snapshot, not
to `api.players` (it's not per-player) and not to `api.product_options`
(it's not a knob). Putting it in `api.product_snapshot.methodology_combos`
keeps it versioned with the snapshot — a bake that changes the methodology
copy bumps `snapshot_id`.

#### 3.5.4 Ownership

- **Backend-owned.** Source: the bake pipeline's snapshot job writes a new
  row per bake and flips `is_active=true` only after the publish gate
  passes (§6).
- **Frontend-readonly.**

#### 3.5.5 Lineage

The snapshot IS the lineage root. Every `bake_id` in
`api.player_values.bake_id` resolves back to a snapshot.

#### 3.5.6 Freshness

`built_at` is **not** freshness. Content freshness is per-source in
`sources[<source>.content_vintage]` (the publisher's content date, not the
pull time) and per-row in `api.player_values` (§3.1.9).

---

## 4. Cross-surface join map

The FE joins exclusively on `player_key` (number) and `source` (text). No
other cross-surface key is allowed:

| join | from | to | key |
|---|---|---|---|
| values ↔ players | `api.player_values` | `api.players` | `player_key` |
| values ↔ snapshot (source meta) | `api.player_values` | `api.product_snapshot.sources[<source>]` | `source` |
| context ↔ players | `api.player_context` | `api.players` | `player_key` |
| context meta ↔ snapshot | `api.player_context` (meta) | `api.product_snapshot.context_meta` | one-to-one (joined at fetch) |
| values tier vectors ↔ snapshot | `api.player_values.tier_price_vector` | `api.product_snapshot.pie_vintage_per_source[source]` | source + tier_price_vintage ≤ pie_vintage |
| options ↔ snapshot version | `api.product_options` | `api.product_snapshot.contract_version` | equality; mismatch → fail-closed |

No name-based joins. The inventory flags "team-level buckets (106=Jets,
108=Bills) with no distinguishing flag" as a soft spot; v1 does not
introduce a separate team-bucket table — those rows live in
`api.player_context` keyed on `player_key`, and team is never a join key.

---

## 5. Fail-closed semantics (per surface)

Every surface has explicit fail-closed semantics. "Fail-open" (silently
degrade) is reserved for the **documented** cases the inventory calls out —
and v1 narrows them.

### 5.1 Fail-closed (refuse to render)

| surface | condition | FE behavior |
|---|---|---|
| `api.player_values` | contract_version mismatch (§7) | refuse; render "Data contract version mismatch — see Chart Health" |
| `api.player_values` | `pie_vintage < bake_id` for any visible row | refuse; render "Indexed values pinned to a stale pie — see Chart Health" |
| `api.player_values` | `tier_price_vintage != bake_id` when `tier_price_vector IS NOT NULL` | refuse; render "Tier calibration vintage mismatch — see Chart Health" |
| `api.player_values` | source's `source_validation[source] != 'live'` | refuse the **source** (render "—" with red border for that source only); the rest of the chart renders |
| `api.player_values` | any source key in `api.product_options.source_keys` missing a row | refuse; the same way `runRegressionGuards.sourceMapCoverage` refuses today |
| `api.players` | empty result | refuse; render "Canonical player records are unavailable." (same as inventory §6) |
| `api.product_snapshot` | no row with `is_active=true` | refuse; render "No active snapshot — pipeline is offline" |
| `api.product_snapshot` | `source_validation[<key>]` missing for any key in `api.product_options.source_keys` | refuse; same throw as inventory |
| `api.product_options` | contract_version mismatch with snapshot | refuse (§7) |

### 5.2 Fail-open (documented degradation)

The inventory lists 4 fail-open paths today. v1 **preserves all 4** because
each is intentional and called out as such in the code. None of them is
silent in the sense of being invisible:

| path | inventory reference | v1 behavior |
|---|---|---|
| `adjustment-inputs.json` fetch/schema fail | `curve-widget.js:723-736` | `api.player_values.tier_price_vector` absent for the affected source → that source's `_adjusted` curve pauses; chart still renders. The pause is rendered visibly with a banner ("source paused — no stage-2 cells") and the `runRegressionGuards.adjustmentCellCompleteness` check. |
| `player-news.json` fetch fail | `comparison-dashboard.js:168-169` | `api.player_context` returns empty; news column renders "No recent news"; the JEG-326 watcher page is the upstream safety net. |
| `reference-freshness.json` / `player-news.json` fetch fail in inline health card | `index.html:2246-2247` | Health card not rendered; the rest of the chart renders. |
| `scaleToSharedTotal` / `shapeToAnchorPeaksThenSharedTotal` no basis | `value-model.js:151, 176` | Returns identity copy of values. This is **mathematical** fail-open (no data), not network fail-open — and stays as-is. |

### 5.3 What v1 REMOVES from fail-open

The inventory's "fail-open" list also includes five latent-bug or
soft-spot items that v1 treats as **fail-closed** instead:

| inventory item | v1 treatment |
|---|---|
| Export button `link.href = blob` coerces to `"[object Blob]"` (latent bug) | Reported to risk-register; not a contract issue but a Phase D item |
| `buildEspnIndexedMap` duplicate declaration (line 604 vs 630) | Fail-closed: contract spec says exactly one declaration; Phase D consolidation. |
| `commonFixedPieTotal` uses median (not sum) across source totals | Documented as **explicitly the median** in `api.player_values.index_total` semantics; the publish gate (§6.1) requires the median to match the pipeline's pie identity. |
| `team` `"—"` fallback for teamless players | Rendered as "FA" with visible flag; rows still priced and ranked. |
| `news_by_player_key` string→Number coercion with no key validation | Contract requires `player_key` to be `bigint`; mismatches are fail-closed (`api.player_context` rejects the row). |

---

## 6. Publish gate (atomic snapshot/publish)

The brief mandates: "The publish gate must check indexed values against
same-bake pie targets (no rescale/pin to a pie older than its inputs) — the
contract must carry pie vintage per source to make that check possible."

### 6.1 Pie vintage guard

For every `api.player_values` row with `view='combo_reindexed'` and
`value_provenance IN ('indexed', 'vorp_indexed', 'ddf_translated')`:

```
assert row.pie_vintage == row.bake_id
       OR row.pie_vintage IS NULL  -- passthrough sources not on the pie
```

If the assertion fails, the row is **withheld** from the snapshot
(snapshot row assembly refuses, transaction rolls back). The publish gate
never publishes a snapshot with a stale pie. The contract surfaces
`api.product_snapshot.pie_vintage_per_source[<source>]` so the FE can
verify this **after** the snapshot is published (defense in depth), but the
gate itself runs in Supabase pre-publish.

### 6.2 Atomic snapshot/publish

The pipeline writes one `api.product_snapshot` row per bake in a single
transaction that includes:

1. INSERT into `public.consolidated_values` (bake rows).
2. INSERT into `public.player_news` / `public.player_adjustments` (context).
3. INSERT into `public.product_options` (defaults — only on first run;
   subsequent runs UPDATE).
4. Refresh materialized view `api.player_values_coverage` (the per-view
   coverage metadata).
5. Compute pie_vintage_per_source from the just-written
   `public.consolidated_values`.
6. INSERT into `api.product_snapshot` with `is_active=false`.
7. UPDATE old active row `is_active=false`.
8. UPDATE new row `is_active=true`.
9. Run the pie-vintage guard (SELECT asserting no row violates it).
10. COMMIT (or ROLLBACK on any failure).

The `is_active` flip is the atomic publish. Readers (FE) always select
`is_active=true`. There is no partial-state window.

### 6.3 12-combo headless sweep (Phase D gate, not Phase B)

The brief's standing rule: "Before changing the trade-value chart — Run
the 12-combo headless sweep (3 scorings × 4 league sizes) against the
built `dist/`, and check `fixedPieIndexed` and `sourceScaleAgreement` in
`TradeValueCurveDiagnostics` for each." The contract does **not** embed
this sweep — it ships `api.player_values` and `api.product_snapshot` such
that the existing sweep still passes. Phase D owns the sweep integration.

---

## 7. Versioning and fail-closed semantics

### 7.1 `contract_version` format

`MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible: field renames, grain changes, fail-closed
  condition changes. Old FE refuses immediately.
- **MINOR** — additive: new optional fields, new rows in `source_keys`,
  new `view` values (the future vorp_on_demand). Old FE may not render
  the new fields but must render the rest correctly.
- **PATCH** — internal-only: bug fixes, no schema impact.

### 7.2 v1 starting version

`1.0.0` for the first publish. The contract reserves the following
MINOR-extension points:

- `view='vorp_on_demand'` — the JEG-329 rework, conditional on Jeremy's
  methodology call.
- `view='vorp_combined'` — combined VORP across as-published + ESPN, future.
- Per-position `bench_share` (the inventory's `skillBenchShares` already
  supports it; v1 ships global `bench_share` only).
- Custom `roster_shape` beyond the 4 named shapes.

### 7.3 Fail-closed on unknown version

```
const KNOWN_VERSIONS = new Set(["1.0.0"]);
if (!KNOWN_VERSIONS.has(snapshot.contract_version)) {
  throw new Error(`Unknown contract version ${snapshot.contract_version}. Render refused.`);
}
```

The FE NEVER silently falls back to legacy fixture paths. The legacy
`assets/comparison-sources-data.json` path becomes **deprecated** on
contract v1 publish (Roman's call: keep shipping it for one release as a
back-compat fallback, then delete).

### 7.4 Backward compat strategy

v1 ships with both surfaces live for **one release**:
- `api.player_values` / `api.players` / `api.player_context` /
  `api.product_options` / `api.product_snapshot` (new).
- `assets/comparison-sources-data.json` / `assets/players.json` /
  `assets/player-news.json` / `assets/adjustment-inputs.json` /
  `reference-freshness.json` (old).

The FE `product-data.js` reads the contract surfaces as primary; on a
contract_version mismatch or fetch failure it refuses (NOT falls back).
Roman owns the deprecation timeline.

---

## 8. FE adapter interface (`product-data.js`)

The single module that talks to the contract. v1 spec:

```javascript
// app/trade-value-chart/assets/product-data.js
// v1.0.0 — JEG-327 contract
//
// This is the ONLY module that reads from the contract surfaces.
// All other code in app/trade-value-chart/ calls into this module.
//
export async function initProductData({ contractVersion = "1.0.0" } = {}) {
  // 1. Fetch api.product_snapshot WHERE is_active=true.
  // 2. Verify snapshot.contract_version === contractVersion. Else throw.
  // 3. Fetch api.product_options (singleton).
  // 4. Verify options.contract_version === snapshot.contract_version. Else throw.
  // 5. Fetch api.players (single batch).
  // 6. Fetch api.player_values (paginated; or full snapshot in v1).
  // 7. Fetch api.player_context (paginated).
  // 8. Return the frozen product data handle below.
}

export function getPlayerValues({ source, scoring, teams, qbVariant, view }) { /* … */ }
export function getPlayers() { /* canonical identity */ }
export function getPlayerContext(playerKey) { /* news + adjustments */ }
export function getProductOptions() { /* bench_share bounds, defaults, key lists */ }
export function getSnapshot() { /* api.product_snapshot row */ }
```

### 8.1 Semantic method contracts

- `getPlayerValues({source, scoring, teams, qbVariant, view})` returns a
  frozen `{ values: Map<playerKey, number>, tier_price_vector: object|null,
  pie_vintage: string, bake_id: string, coverage_class: 'full'|'view_limited_combo'|'view_limited_source', value_provenance, model_vs_published, detail_locator }`. The FE renders the value, the
  provenance badge, and the coverage-class fallback from this single object.
- `getPlayers()` returns a frozen array of `api.players` rows keyed by
  `player_key`. K/DST are present; `kdst_excluded_from_chart=true` is the
  FE's filter signal.
- `getPlayerContext(playerKey)` returns a frozen `{ news: [...],
  adjustments: [...], as_of: ISO8601 }` or `null` (no news/adjustments).
- `getProductOptions()` returns the singleton frozen.
- `getSnapshot()` returns the active `api.product_snapshot` frozen.

### 8.2 Initialization gate

`initProductData` is fail-closed:
- Any surface fetch fails (network 5xx, parse error) → throws.
- Any contract_version mismatch → throws.
- `api.players` empty → throws.
- `api.product_snapshot` no active row → throws.
- `api.player_values` empty for any key in
  `api.product_options.source_keys` → throws (preserves the
  `runRegressionGuards.sourceMapCoverage` invariant).

### 8.3 Internal window globals (preserved for cross-widget sync)

`product-data.js` continues to expose the four cross-widget globals the
inventory identifies (these are **intra-app wiring**, not contract reads):

- `window.TradeValueSharedState` — selector state out
- `window.TradeValueLockOrder` — lock key string
- `window.TradeValueTwoTierLive` — live cells override
- `window.TradeValueCurveDiagnostics` — guard object (frozen)

These are not contract surfaces. v1 keeps them under
`product-data.js`'s namespace control but does not move them to the
contract.

---

## 9. Phase E — Computation ownership (recommendations)

The brief mandates: "Every browser-side economic calculation inventoried,
assigned to backend-owned / frontend-interaction transform / presentation-only,
with parity-test requirements."

### 9.1 Inventory and assignment

| calculation (file:line) | today's owner | recommended owner | parity test |
|---|---|---|---|
| `value-model.js` pure functions (all 508 lines) | browser | **backend-owned reference; FE keeps versioned interaction transforms** | Existing two-callers drift test (the file's own docstring); contract surfaces must reproduce `roleMap`, `normalizeToFixedPie`, etc. at the row level. |
| `curve-widget.js:195-584` (`TwoTier` module) | browser (live solve) | **backend-owned**; FE uses `vector+blend` (§9.2). | **Parity test:** blend vs current browser solve across the full slider range for every combo. Pass = exact or sub-display-unit agreement. |
| `curve-widget.js:1991-2041` (`refitLiveCells` OLS) | browser (live OLS) | **backend-owned.** The bake produces cells; FE reads from `api.player_values.tier_price_vector` (or from `api.product_options` for live cells if global weights change — Phase D). | OLS identity at default bake cells (current pinned regression). |
| `curve-widget.js:1436-1494` (`buildLiveAdjustedMap`) | browser | **backend-owned** (`tier_price_vector`'s `adjusted_*.alpha`/`beta` if extended, else a precomputed `api.player_values` view). | Same parity. |
| `curve-widget.js:1117-1255` (`buildVorpRows` raw-VORP economics) | browser | **backend-owned.** Bakes vorp/vorp_indexed/adj_values rows. | Vorp-row identity at default share. |
| `curve-widget.js:1867-1885, 1899-1968` (`ddfTwoTierValues`) | browser (live) | **backend-owned** (baked into `tier_price_vector`); FE blends. | Parity. |
| `curve-widget.js:1781-1837, 1839-1861` (`twoTierConfig`, `twoTierCalibration`) | browser (cache) | **backend-owned.** | Cache hit must match. |
| `curve-widget.js:1532-1598` (`rebuildDomain`) | browser (orchestration) | **frontend-interaction transform** — FE composes the rows into a chart; backend rows are inputs. | N/A (composition, not math). |
| `curve-widget.js:3393-3493` (`runRegressionGuards` 12 checks) | browser | **backend publish-gate** for the data; FE re-runs the same 12 checks as **defense in depth**. Parity = same `guardsPassed` boolean. | Same assertion. |
| `curve-widget.js:2974-3048` (`fixedPieDiagnostics`) | browser | **backend publish-gate.** | Same. |
| `curve-widget.js:1380-1409` (`buildCbsAdjustedMap`) | browser | **backend-owned.** | Identity at the published-cell fixture. |
| `curve-widget.js:1340-1378` (`applyRosterShape`) | browser | **frontend-interaction transform** (presentation only). | N/A. |
| `comparison-dashboard.js:521-592` (`buildVorpRows`) | browser | **backend-owned.** | Identity. |
| `comparison-dashboard.js:265-286` (`buildLiveAdjustedMap`) | browser | **backend-owned.** | Identity. |
| `comparison-dashboard.js:648-677` (`buildCbsAdjustedMap`) | browser | **backend-owned.** | Identity. |
| `comparison-dashboard.js:487-497` (`normalizeTradeChartToFixedPie`) | browser | **frontend-interaction transform** (wrapper around `ValueModel.normalizeToFixedPie`). | Identity. |
| `comparison-dashboard.js:423-434` (`normalizedAdjustedMapFor`) | browser | **frontend-interaction transform.** | Identity. |
| `comparison-dashboard.js:679-703` (`rebuildSourceMaps`) | browser | **frontend-interaction transform.** | Identity. |
| `comparison-dashboard.js:98-109` (`weekForSource`) | browser | **frontend-interaction transform** (selector logic). | N/A. |
| `comparison-dashboard.js:768-803` (`normalizeNewsEntry`) | browser | **frontend-interaction transform** (display). | N/A. |
| `comparison-dashboard.js:805-832` (`normalizeAdjustmentEntry`) | browser | **frontend-interaction transform.** | N/A. |
| `comparison-dashboard.js:1160-1164` (export button) | bridge | Reported to risk-register (latent bug). | Phase D fix. |
| Display formatting (`pieDisplayTenths`, `formatOne`, `formatTwo`) | browser | **presentation-only** (stays in browser). | N/A. |
| DOM event listeners / window globals | browser | **intra-app wiring** (stays in browser). | N/A. |

### 9.2 `vector+blend` — the bench-share slider at the browser

Per the 2026-10-03 direction:

```javascript
// product-data.js — sketch only; full impl in Phase E
function previewBlend(row, tierPriceVector, benchShare) {
  // tierPriceVector: {QB:{starter:pbs,bench:pbb,...}, RB:..., ...}
  // benchShare: 0..1
  // row: {player_key, pos, value (baked full-precision)}
  const pos = row.pos;
  const tier = row.tier; // 'starter' | 'bench' — derived from roleMap
  const tierPrice = tierPriceVector[pos][tier];
  // Blend: starter-tier price when share=0, bench-tier price when share=1
  return tierPrice.starter * (1 - benchShare) + tierPrice.bench * benchShare;
}
```

~10 lines of arithmetic. The pipeline precomputes `tierPrice.starter` and
`tierPrice.bench` once per combo; the slider is instant across the full
feasible interval.

**Acceptance gate:** the parity test compares `previewBlend(...)` to the
current `TwoTier.calibratePositionFeasible` result across the full slider
range for every combo. Pass = exact or sub-display-unit agreement (values
render to one decimal). **If tier assignment turns out to be soft
(share-dependent) rather than a hard partition, blend is an approximation
— the parity test decides, not an assumption.**

---

## 10. Phase A verification report

### 10.1 Coverage check

The Phase A inventory at `docs/contract/fe-dependency-inventory.md`
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

### 10.2 Gaps discovered (and addressed by v1)

The inventory flagged the following items. v1 addresses each:

| inventory gap | v1 surface / fix |
|---|---|
| `assets/reference-freshness.json` (not in ticket list) | `api.product_snapshot.reference_freshness` (§3.5.2) |
| `methodology-data` inline island (not in ticket list) | `api.product_snapshot.methodology_combos` (§3.5.3) |
| `espn_zeroed` denormalized array | `api.players.ir_zeroed` (per-row) + `api.product_snapshot.espn_zeroed` (snapshot-level denormalization for cross-widget consistency) (§3.2.2, §3.5.2) |
| 4 RSS feeds (dead metadata) | EXCLUDED — do not enter the contract (§2 justification) |
| External publisher URLs in footnotes | EXCLUDED — user-clickable, not fetched (§2 justification) |
| Google Fonts CSS | EXCLUDED — styling, not data (§2 justification) |
| 3 CSS files | EXCLUDED — styling (§2 justification) |
| `comparison-dashboard.js` export button latent bug | Reported to risk-register (§5.3); Phase D |
| `buildEspnIndexedMap` duplicate declaration | Fail-closed in contract spec (§5.3); Phase D consolidation |
| `comparison-dashboard.js:1288` universeSize double-counts | Phase D fix (contract doesn't mandate the number; FE computes correctly) |
| `full_name ‖ name ‖ ""` chain | `api.players.canonical_name` (single canonical field); FE drops the chain (§3.2.2) |
| K/DST in fixture, hidden by widgets | `api.players.pos='K'\|'DST'` + `kdst_excluded_from_chart=true` (§3.2.2) |
| `weeks_out_range` etc. enum strings | `api.player_context.adjustments[]` carries the verbatim JSON; contract spec pins the status enum values: `{Out, Doubtful, Questionable, IR, PUP, "Out (protocol)", "IR (season-ending…)"}` (preserves today's prose; future MINOR bump can pin a tighter enum). |
| `pie_source` ships CI absolute path | EXCLUDED — `pie_vintage_per_source` carries a bake_id, not a path |
| News `url` fields (~280 read-more links) | `api.player_context.news[].url` carries them (UI renders; not contract-breaking) |
| `window.TradeValueLockOrder` / `TradeValueSharedState` cross-widget contract | Preserved as `product-data.js` intra-app wiring (§8.3); not a contract surface |
| Dead `#valueModeSeg` control | Removed by `makeValueModeControl` already; contract doesn't reference it |
| Dead dynamic `benchMixFor` (only `legacyBenchMixFor` runs) | Backend owns `legacyBenchMixFor` post-Phase E; FE never calls it |

### 10.3 Open questions from the inventory (resolved in §11 below)

The inventory's §9 lists 16 open questions. v1 resolves 14 of them
inline. The remaining 2 go back to the JEG-327 ticket for Jeremy (see
§11).

---

## 11. Open questions / decisions needed from Jeremy

These are methodology-adjacent decisions that **cannot be made by the
contract author**. Each gets a ticket comment on JEG-327 (Roman posts
per the lane adaptation).

1. **`full_name` vs `name` canonical** (inventory §9 #9) — v1 picks
   `canonical_name` as a single field. **If Jeremy prefers** keeping the
   fixture's `name` and surfacing it as `name` in the contract, say so.
   The build's canonical naming table (`public.players`) is the authority;
   the contract field name is a presentation decision.

2. **`MIN_SHARED_FOR_PIE = 40`** (inventory §9 #2) — v1 freezes it at 40
   and ships it on `api.product_options.min_shared_for_pie`. **If Jeremy
   wants** this as a defensive constant the FE can override per-deployment,
   say so; otherwise v1 freezes it.

   (The remaining inventory questions — `STARTER_MARKUP_SANE_*`,
   `PEAK_AGREEMENT_*`, `players-data` versioning, `commonFixedPieTotal`
   median match, the 3 espn_zeroed vs fixture-ir-flag questions, the
   `data.player_keys` typing, `cbs_adjusted` combo source, K/DST boundary,
   `weeks_out_range` enum tightening, `adjustment-inputs.json` fallback
   asymmetry, news `url` rendering, dead `#valueModeSeg`, and the
   `weekly_vegas` cross-widget globals — v1 picks one resolution each and
   documents it above. If any of these choices is wrong, the JEG-327
   ticket comment is the place to flag.)

---

## 12. Migration sequencing — Phase D order

The brief mandates: "Phase D order: curve widget, comparison dashboard,
context/news, selectors, remaining with acceptance gates per cutover."

### 12.1 Phase D order

1. **Curve widget cutover** (highest blast radius; ships first).
   - Acceptance: parity test passes (vector+blend vs live solve);
     `fixedPieIndexed` and `sourceScaleAgreement` both TRUE in
     `TradeValueCurveDiagnostics` for all 12 (scoring × teams) combos;
     the 12-combo headless sweep is green;
     `make validate` is green.

2. **Comparison dashboard cutover** (depends on curve widget reading from
   `product-data.js`; ships second).
   - Acceptance: every value column renders from `getPlayerValues(...)`;
     no value comes from a raw fixture path;
     `comparison-dashboard.js` has zero direct reads of the legacy
     fixtures.

3. **Context/news cutover** (depends on comparison dashboard's
   `api.player_context` calls; ships third).
   - Acceptance: news and adjustments render from `getPlayerContext(...)`;
     the JEG-326 watcher page is green;
     no direct fetch of `player-news.json`.

4. **Selectors cutover** (depends on context/news; ships fourth).
   - Acceptance: every default (scoring, teams, roster_shape,
     bench_share, position_weights, lock_order, view_mode,
     reference_source) reads from `getProductOptions()`;
     no FE-side constants for any of them.

5. **Remaining** (methodology data, health, methodology renderer, JSX for
     release tool, finance inspection) — ships last.
   - Acceptance: every remaining read goes through `product-data.js`;
     the `reference-freshness.json` SHA enforcement becomes a real warning
     (the SHA gate is `enforced: false` today — Phase D enables it on
     contract cross-check).

### 12.2 Acceptance gate (every Phase D cutover)

- `make validate` green (which runs the existing test suite).
- Phase E parity test green (vector+blend vs live solve, full slider
  range, every combo).
- 12-combo headless sweep green (`fixedPieIndexed`,
  `sourceScaleAgreement` both TRUE).
- `runRegressionGuards.guardsPassed === true` for every visible combo.
- Every regression guard has a **negative test** against a simulated
  broken state (the standing rule from the AGENTS.md: "Every regression
  guard must prove it catches the bug it names. Negative-test it against
  a simulated broken state.")

---

## 13. Security — staged RLS/grants hardening plan

The brief mandates: "Security: staged RLS/grants hardening plan
(inventory consumers → contract → grants → restrict internal tables →
verify prod). Do NOT bulk-enable RLS. DDL goes through the Supabase SQL
editor; after DDL run `NOTIFY pgrst, 'reload schema'` (schema-cache lag);
PostgREST savers use bare table names."

### 13.1 Stage 0 — inventory consumers (today)

Today every FE fetch goes through `window.TRADE_VALUE_*` keys + RLS-off
public reads (PostgREST). No auth.

### 13.2 Stage 1 — create the contract surfaces (Phase B → Roman)

- Create `api.player_values` (a VIEW projecting
  `public.consolidated_values`).
- Create `api.players` (a VIEW projecting `public.players`).
- Create `api.player_context` (a VIEW union of `public.player_news` +
  `public.player_adjustments`).
- Create `api.product_options` (a TABLE, one row keyed `product_key`).
- Create `api.product_snapshot` (a TABLE with `is_active` flag).
- Create the new underlying tables (`public.player_news`,
  `public.player_adjustments`, `public.player_review`,
  `public.product_options`, `public.product_snapshot`) — the pipeline
  writes them; the views expose them.

**No RLS changes yet.** The FE keeps working via the legacy fixture paths.

### 13.3 Stage 2 — FE reads from contract (Phase D, in lockstep with cutover)

- `product-data.js` reads `api.*` via PostgREST (anon key).
- `api.player_values`, `api.players`, `api.player_context`,
  `api.product_snapshot`, `api.product_options` get `anon SELECT` grants.
- The legacy fixtures keep their PostgREST exposure for one release as a
  back-compat fallback.

### 13.4 Stage 3 — restrict internal tables

After one release of contract-only reads:

- `public.consolidated_values` — restrict `anon SELECT` to the api view;
  direct reads are now service_role-only (the JEG-322 monitoring reads
  health tables the same way).
- `public.players` — same.
- `public.player_news`, `public.player_adjustments`, `public.player_review`
  — same.
- `public.product_snapshot`, `public.product_options` — same.
- `api.*` views keep `anon SELECT` (FE).

### 13.5 Stage 4 — verify prod

- Run the JEG-322 health check (Phase C dependency).
- Run a probe PostgREST query against each `api.*` view as anon — must
  return 200.
- Run a probe query against `public.consolidated_values` as anon — must
  return 401/403 (after Stage 3).
- Confirm `make validate` green; `runRegressionGuards` green on prod
  artifact.

### 13.6 Standing rules (do NOT violate)

- **Do NOT bulk-enable RLS.** Enable per-table in the order above.
- **Do NOT use FORCE RLS** (would break service_role pipeline writes — see
  migration 001 §6 comment).
- **DDL goes through the Supabase SQL editor.** PostgREST cannot run DDL.
  After every DDL: `NOTIFY pgrst, 'reload schema';` (schema-cache lag —
  cbsros precedent).
- **PostgREST savers use bare table names** (`cbs_ros_projections`, not
  `public.cbs_ros_projections` — the sbclient builds
  `/rest/v1/<table>`).

---

## 14. Sequencing note for JEG-325

JEG-325 (Todo, strangler-fig migration of current consumers) is **on hold
pending the v1 contract**. The brief asks for a recommendation: ride behind
the v1 contract, or re-scope as JEG-327 Phase D.

**Recommendation: re-scope as JEG-327 Phase D.** The strangler-fig
migration's per-cutter sequence (curve widget → comparison dashboard →
context/news → selectors → remaining) IS the Phase D cutover sequence
above. Renaming it as Phase D:

- Removes the artificial "strangler-fig" framing (the inventory shows the
  FE only ever reads through ONE module after v1; there's nothing to
  strangler — the legacy fixtures are deprecated together with the
  contract cutover).
- Aligns the two JEGs on a single acceptance gate (parity test +
  12-combo sweep).
- Lets Phase E (computation ownership) and Phase C (JEG-322 publish gate)
  feed cleanly into the same cutover.

**Roman posts this recommendation as a comment on the JEG-327 ticket**
(the lane adaptation routes the comment through Roman, not via the Linear
CLI which is unavailable to M3 on this host).

---

## 15. Acceptance checklist

- [x] docs/contract/fe-read-contract-v1.md exists with grain/fields/types/
      ownership/lineage/freshness/versioning for all five surfaces.
- [x] A SQL draft at sql/contract/api_v1.sql defines the api.* views/tables
      projecting from public.consolidated_values and the other backend
      sources, with grants/RLS sketched (NOT applied).
- [x] The Phase A verification report (§10) lists every required file as
      covered or names the concrete gap.
- [x] Migration sequencing (§12) + computation-ownership recommendations
      (§9) are documented; sequencing note for JEG-325 (§14) is a
      recommendation Roman posts to the JEG-327 ticket.
- [x] `make validate` not run (doc-only; per standing rule: "doc-only is
      fine but say so"). No code touched in this Phase B draft.

---

## 16. Phase B summary

Phase B is contract definition + sequencing only. No DDL, no migration
build, no pipeline edits, no FE edits. The contract specifies five
semantic FE-facing surfaces (`api.player_values`, `api.players`,
`api.player_context`, `api.product_options`, `api.product_snapshot`),
each with grain/fields/types/ownership/lineage/freshness/`contract_version`.
It honors the JEG-331 ground truth (per-view coverage metadata with
explicit "not available for this combo" semantics, versioned extension
points for the JEG-329 rework). It carries per-row VALUE PROVENANCE
(`native`/`indexed`/`ddf_translated`/`vorp`/`vorp_indexed`/`adj`) and
per-row `model_vs_published` (`model`/`published`), plus
`tier_price_vector` for vector+blend bench share. The bench-share bounds
(default 0.15, user-settable, bounded [0.01, 0.30]) ship on
`api.product_options`. The publish gate verifies
`pie_vintage == bake_id` (no rescale to a stale pie). `contract_version`
is `1.0.0`; unknown versions fail-closed. `product-data.js` is the
single FE adapter. Phase D sequencing (curve widget → comparison
dashboard → context/news → selectors → remaining) and Phase E
computation ownership (backend-owned reference implementations; FE
keeps versioned interaction transforms; vector+blend bench share;
parity test as the acceptance gate) are recommendations for Jeremy's
call. Security hardening is staged (Stage 0–4). The recommendation for
JEG-325 is re-scope as JEG-327 Phase D.
---

## 17. v1.1 additive surfaces (JEG-432 R5 freshness, R1 pair registry)

Added 2026-10-06 as MINOR extensions (§7.1). The runtime `CONTRACT_VERSION`
constant stays `1.0.0` until the api.* cutover publishes them server-side;
an old FE ignores them and renders the rest correctly.

### 17.1 Calendar

Freshness uses the **content calendar** of `pipelines/nfl_week.py` (week
turns over on Tuesday, after Monday night; content week 1 starts Tue
2026-09-08). Not the watchdog calendar (`ops/watchdog/_common.nfl_week`,
Thursday flip; GAP-WEEK-CALENDARS). Copies: `product-data.js`
`contentWeekForDay` (reader's day in America/New_York) and SQL
`public.nfl_content_week(date)`; both pinned to `nfl_week.py`
(`tests/test_source_freshness.py`, and a 200-day SQL check in the log).

### 17.2 `getSourceFreshness()` (FE adapter, over the shipped snapshot)

Per chart series (`source_keys` plus the three VORP vs waivers series):
`vintage_week`, `vintage_basis` (`week_designated` | `content_vintage` |
a dated field such as `vintage`/`espn_snapshot`/`fetched_at`), `cadence`
(`weekly` | `rest_of_season`), `current_content_week`, `status`
(`current` | `older` | `unknown`), `is_older_week`, `weeks_behind`,
`excluded_on_first_load`. `*_adjusted` series are dated by their raw chart.

First load: `first_load_reference_week` = the newest week any weekly
chart has reached, capped at the content week. Weekly charts older than
it are in `first_load_excluded` and start switched off; the reader can
turn them on. Rest-of-season projections (ESPN, CBS ROS, Razzball) are
flagged but never excluded (ESPN is the anchor). When every weekly chart
is behind the content week (e.g. Tuesday before publishers post), nothing
is excluded and every chart still shows `status: "older"`.

### 17.3 `getPairRegistry({scoring, teams})` (FE adapter)

One row per (source, method): 7 sources × 3 methods (`adjusted` = "Our
Data Driven Adjustments", `indexed` = "Indexed", `vorp_vs_waivers` =
"VORP vs waivers"; copy-vorp-001 replaces the design's "Pure VORP").
Fields: `source`, `source_label`, `method`, `method_label`, `series_key`
(null when not offered), `is_default_method`, `available`,
`excluded_on_first_load`, `reason_code`, `reason_text`, `vintage_week`,
`vintage_basis`, `vintage_status`, `shared_players`.

`reason_code` (null when the pair is available and on by default):

| code | available | derived from |
|---|---|---|
| `not_offered` | false | the design's allowed-pair matrix |
| `league_setting_unsupported` | false | no saved combo for the reader's scoring × teams (until R3 derivation ships) |
| `insufficient_overlap` | false | priced chart players < `min_shared_for_pie` |
| `adjustment_pending` | false | the adjusted curve is paused (no complete live adjustment cells) |
| `stale_vintage` | **true** | `excluded_on_first_load` from §17.2 — selectable, just off at first load |

### 17.4 `api.source_freshness` (Supabase view)

Migration `supabase/migrations/jeg432_source_freshness.sql`. One row per
source: the newest week SAVED in its Supabase source table vs the content
week (`latest_week`, `latest_content_date`, `latest_pulled_at`,
`latest_week_rows`, `current_content_week`, `status`, `is_older_week`,
`weeks_behind`). This describes saved inputs; the published chart's
vintage is §17.2 and can lag it until the next bake. ESPN is dated by
`espn_snapshot_date` (its `week` column is not a content week).

### 17.5 `api.source_inputs_weekly` / `api.source_input_weeks` (R4, Supabase views)

Migration `supabase/migrations/jeg432_r4_source_inputs_weekly.sql`. The
saved 12-team / 1-QB published inputs per source × week × scoring
(FantasyCalc, FantasyPros, USA Today, CBS), so the browser can run the
same league derivation on the current week and the week before (movers).
Grain: one row per (source, season, week, scoring, player_key), from the
LATEST pull of that week. Fields: `week`, `weeks_back_from_latest`
(0 = newest saved week for that source), `weeks_back_from_content_week`,
`scoring` (full/half/standard), `teams` (12), `qb_slots` (1),
`player_key`, `player_norm`, `position`, `team`, `native_value`,
`value`, `source_content_date`, `pulled_at`, `bake_id`.
`api.source_input_weeks` is the per-week metadata (player counts, pull,
bake). The FE picks `week = <chart vintage week> - 1` for the prior week.
Projection sources (ESPN, CBS ROS, Razzball) have no prior-week saves in
this shape yet (GAP-R4-PROJECTION-HISTORY).
