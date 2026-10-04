# JEG-327 Phase A — Frontend Dependency Inventory (checked-in matrix)

**Ticket:** JEG-327 — Define FE/BE boundary and versioned frontend read contract
**Phase:** A — inventory current FE reads and calculations
**Date:** 2026-10-03
**Method:** 8 parallel read-only M3 analysis workers (one per file/sweep); reports in `lanes/inbox/minimax/JEG-327-inventory-*.json`; assembled by Roman. No repo files were modified by the workers.
**Frontend root:** `app/trade-value-chart/` (`index.html` + `assets/`)

**Coverage vs the ticket's required file list:** all 8 required inputs inventoried —
`curve-widget.js`, `comparison-dashboard.js`, `value-model.js`, `index.html`,
`comparison-sources-data.json`, `players.json` (via the `players-data` inline island + staged fixture),
`player-news.json`, `adjustment-inputs.json`.
**Additionally discovered (not in the ticket's list):** `assets/reference-freshness.json` (fetched by the
inline health card), the `methodology-data` inline JSON island in `index.html` (~330KB of real data),
and the 3 local CSS files.

---

## 1. Complete load inventory (what the browser actually loads)

### 1.1 Static tags in `index.html`

| file:line | mechanism | path | notes |
|---|---|---|---|
| `index.html:4` | `<meta name="trade-chart-build">` | `tv-20261002-0803-db9f76f` | single source of build identity |
| `index.html:10` | `<link rel="icon">` | inline `data:image/svg+xml` | favicon; `icon.jpg` on disk is unreferenced |
| `index.html:12-13` | `<link rel="preconnect">` | `https://fonts.googleapis.com`, `https://fonts.gstatic.com` | external |
| `index.html:14` | `<link rel="stylesheet">` | Google Fonts CSS (Archivo + IBM Plex Mono) | external; pulls woff2 from fonts.gstatic.com at runtime |
| `index.html:15` | `<link rel="stylesheet">` | `assets/curve-widget.css` | no cache-buster |
| `index.html:16` | `<link rel="stylesheet">` | `assets/comparison-dashboard.css` | no cache-buster |
| `index.html:17` | `<link rel="stylesheet">` | `assets/dashboard-integration.css` | no cache-buster |
| `index.html:1880` | `<script defer>` | `assets/value-model.js?v=tv-20261002-0803-db9f76f` | pure model module |
| `index.html:1881` | `<script defer>` | `assets/curve-widget.js?v=tv-20261002-0803-db9f76f` | 3564 lines |
| `index.html:1882` | `<script defer>` | `assets/comparison-dashboard.js?v=tv-20261002-0803-db9f76f` | 1330 lines |
| `index.html:1883` | inline `<script id="methodology-data" type="application/json">` | ~330KB JSON island | `{default_combo, bench_share, combos: {<scoring>_<teams>: {scoring, scoring_label, teams, position_shares, adjustments}}}` — real data, not markup |
| `index.html:1884-2220` | inline IIFE | methodology renderer | reads `methodology-data`, `TradeValueSharedState`, `TradeValueTwoTierLive` |
| `index.html:2221` | inline `<script id="players-data" type="application/json">` | ~841KB JSON island | `{meta: {...}, players: [...610]}` — the players identity artifact |
| `index.html:2222-2307` | inline IIFE | data-health renderer | reads `players-data` meta; fetches 3 JSONs (below) |
| `index.html:2308-2326` | inline IIFE | health-dialog wire-up | — |

No `XMLHttpRequest`, no dynamic `import()`, no WebSocket/EventSource, no workers,
no `localStorage`/`sessionStorage`/`IndexedDB` anywhere in the frontend. No `<iframe>`.

### 1.2 Runtime `fetch()` calls

| file:line | URL | cached on | failure mode |
|---|---|---|---|
| `curve-widget.js:707` | `assets/comparison-sources-data.json` | `window.TradeValueComparisonData(Promise)` | throws → page shows "Curves unavailable" |
| `curve-widget.js:727` | `assets/adjustment-inputs.json` | `window.TradeValueAdjustmentInputs(Promise)` | `.catch(() => null)` — fail-open, `_adjusted` curves pause |
| `comparison-dashboard.js:151` | `assets/comparison-sources-data.json` | `window.TradeValueComparisonData(Promise)` | shared single-flight cache with curve widget |
| `comparison-dashboard.js:167` | `assets/player-news.json` | `window.TradeValuePlayerNews(Promise)` | fallback to empty `{meta:{}, news_by_player_key:{}, adjustments_by_player_key:{}}` |
| `comparison-dashboard.js:183` | `assets/adjustment-inputs.json` | `window.TradeValueAdjustmentInputs(Promise)` | `null` on `!ok`, `null` on catch, `null` on schema mismatch |
| `index.html` inline health script (~2246) | `assets/comparison-sources-data.json` | local const | throws → "Dataset health unavailable" badge |
| `index.html` inline health script (~2246) | `assets/player-news.json` | local const | `.catch(() => null)` — card not rendered |
| `index.html` inline health script (~2247) | `assets/reference-freshness.json` | local const | `.catch(() => null)` — card not rendered |

### 1.3 External URLs (user-clickable, not fetched by the app)

- 4 publisher links in the footnotes (`index.html` ~1875): USA Today, FantasyCalc, FantasyPros, CBS (sportsfly CDN) — `target="_blank"`.
- ~280 per-item `url` fields inside `player-news.json` news entries (Yahoo/CBS/NBC/ESPN) — read-more targets; no code was found fetching them.
- 4 RSS feed URLs in `player-news.json` (`meta`-adjacent sources array: PFT, ESPN, CBS, Yahoo RSS) — dead metadata; no code reads them.

---

## 2. Data-reads matrix (by consumer file)

Legend — category: data | metadata | context | selector-config | health | computation.
Proposed surface: `api.player_values` | `api.players` | `api.player_context` |
`api.product_options` | `api.product_snapshot` | none-legacy.

### 2.1 `curve-widget.js` (3564 lines)

| file:line | input | exact path / key | category | proposed surface |
|---|---|---|---|---|
| 707 | `fetch` comparison-sources-data.json | whole payload → `window.TradeValueComparisonData` | data | `api.player_values` |
| 727 | `fetch` adjustment-inputs.json | whole payload → `window.TradeValueAdjustmentInputs` | data | `api.product_options` (stage-2 cells) |
| 892 | `players-data` inline JSON | `players[].player_key` (number), `players[].full_name`/`name`, `players[].team`, `players[].pos`, `players[].espn_ppg.{ppr,half_ppr,standard}`, `players[].rz_ppg.{...}`, `players[].cbsros_ppg.{...}` | data | `api.players` |
| 822 | `data.built_at` | ISO timestamp → next-Monday rollover | metadata | `api.product_snapshot.built_at` |
| 818, 837 | `data.value_weeks.monday` | integer week | metadata | `api.product_snapshot.value_weeks` |
| 998, 1037 | `data.player_keys[sourceId]` | string→int lookup | data | `api.player_values.player_keys` |
| 812-1033 | `data.sources[<key>].combos[<comboKey>]` | per-combo payload | data | `api.player_values.sources` |
| 993 | `combo.values` or `combo.reindexed` | raw chart values | data | `api.player_values.sources[<k>].combos[<c>].values` |
| 994, 1034 | `combo.native` | native published values | data | `api.player_values.sources[<k>].combos[<c>].native` |
| 966, 1404, 3018 | `combo.index_total[<pos>].target_total` | per-position pie target | data | `api.player_values...index_total` |
| 814 | `data.sources[<key>].week_designated` | regex-extracted week | metadata | `api.product_snapshot.sources[<k>].week_designated` |
| 816 | `data.sources[<key>].fit_bake_id` | regex-extracted `fitwk(\d+)` | metadata | `api.product_snapshot.sources[<k>].fit_bake_id` |
| 865, 3506 | `data.source_validation[<key>]` | `"live"` gate; throws if any SOURCE_KEY not live | health | `api.product_snapshot.source_validation` |
| 733 | `payload.schema === "trade-value-adjustment-inputs-v1"` | gate; mismatch → null (fail-open) | metadata | `api.product_options.schema` |
| 598, 618 | `inputs.sources[<rawKey>].status` | `"live"` gate | health | `api.product_options.sources[<k>].status` |
| 603-606 | `inputs.sources[<rawKey>].cells[].{position,tier,alpha,beta}` | affine refit cells | data | `api.product_options.sources[<k>].cells` |
| 3481 | `adjustmentInputs?.version` | bake id string | metadata | `api.product_options.version` |
| 831 | `window.TRADE_VALUE_TODAY` | date override for week rollover | context | none-legacy (test clock) |
| 2764/3508 | `window.TradeValueLockOrder` (write/read) | lock key string | selector-config | `api.product_options` |
| 2622 | `window.TradeValueSharedState` (write) | `{scoring, teams, position, model, lockOrder, rosterShape, benchShare, absenceRate, positionWeights}` | selector-config (out) | `api.product_options` |
| 3482 | `window.TradeValueCurveDiagnostics` (write, frozen) | guard object | health (out) | none-legacy |
| 3526 | `window.TradeValueTwoTierLive` (write) | `{positionWeights()}` | computation (out) | none-legacy |
| 3541 | `window.TradeValueCurveHarness` (write) | harness object | computation (out) | none-legacy |
| — | `ValueModel.*` namespace (from `value-model.js`) | `sourceComboKey, stableTiebreak, allocationCounts, roleMap, projectionRoles, fixedPieDirectionSane, starterMarkupSane, positionalTierScales, shapeToAnchorPeaksThenSharedTotal, scaleToSharedTotal, normalizeToFixedPie, peakAgreement, benchShareOf, MIN_SHARED_FOR_PIE, ...` | computation | hard cross-file dependency |
| — | `globalThis.TradeValueTwoTier` (lines 195-584) | browser port of `pipelines/build_ddf_two_tier_leg.py`: `softplus, sliceExposures, solveTierPrices, feasibleAt, feasibleBenchShareInterval, sliderBounds, roundHalfEven, displayValue, normalizeThenRound, benchMixFor, buildPositionTiers, calibratePosition, calibratePositionFeasible, priceForProjection, skillBenchShares, legacyBenchMixFor, ...` | computation | **methodology lives in the browser here** |
| — | `globalThis.TradeValueCurvePause` (621), `TradeValueCurveGuards` (668), `TradeValueCurveDebug` (673) | `adjustedCurvePaused, defaultIndexedSourceKeys, peaksAboveCollapseFloor, anchorScaleCorrectedCheck, ...` | computation/health | none-legacy |

DOM inputs (controls read): `#curveScoring`, `#curveTeams`, `#posTabs`, `#curveLockOrder`,
bench-share slider (`#benchShareBlock` subtree), position-weight sliders, roster-shape inputs,
`#zoomSeg`/`#zLo`/`#zHi`, `#yLo`/`#yHi`, `#hideZeroTail`, `#curveFindPlayer`/`#curvePlayerSearch`,
`#sourceToggles`, `#valueModeSeg` (dead — removed by `makeValueModeControl`, line 2348).
All are selector-config; none persist (no storage).

### 2.2 `comparison-dashboard.js` (1330 lines)

| file:line | input | exact path / key | category | proposed surface |
|---|---|---|---|---|
| 151 | `fetch` comparison-sources-data.json | whole payload | data | `api.player_values` + `api.product_snapshot` |
| 167 | `fetch` player-news.json | whole payload → `window.TradeValuePlayerNews` | context | `api.player_context` |
| 183 | `fetch` adjustment-inputs.json | whole payload → `window.TradeValueAdjustmentInputs` | data | `api.player_values` (stage-2 cells) |
| 312 | `players-data` inline JSON | `players[].{player_key, full_name/name, pos, team, espn_ppg}` | data | `api.players` |
| 100-101 | `data.sources[key]`, `.fit_bake_id` | per-source object; `fitwk(\d+)` parse | data/metadata | `api.player_values` / `api.product_snapshot` |
| 106, 108, 112, 127 | `data.sources[key].week_designated`, `data.value_weeks.monday`, `data.built_at` | week derivation + rollover | metadata | `api.product_snapshot` |
| 302, 638 | `data.sources[key].combos[comboKeyFor(key)]` | per-combo payload | data | `api.player_values.sources[<k>].combos` |
| 465-466 | `combo.values`, `combo.reindexed`, `combo.native` | sourceId→number maps | data | `api.player_values.sources[<k>].combos[<c>]` |
| 438, 445, 668 | `combo.index_total[<pos>].target_total` | per-position pie target | data | `api.player_values...index_total` |
| 470, 1288 | `data.player_keys[sourceId]`; `Object.keys(data.player_keys).length` | join map; universe count | data | `api.player_values.player_keys` |
| 728 | `data.sources[key].{published, espn_snapshot, fetched_at, vintage}` | date labels | metadata | `api.product_snapshot.sources[<k>]` |
| 756 | `data.sources[key].method_group` | `"ddf-methodology"` etc. → column badges | metadata | `api.product_snapshot.sources[<k>].method_group` |
| 1057 | `data.espn_zeroed[]` | player_key[] flagged ESPN-zeroed | health | `api.product_snapshot.health` |
| 1294 | `data.source_validation[validationKeyFor(key)]` | `"live"/"stale"` | health | `api.product_snapshot.source_validation` |
| 763 | `news.meta.trade_values_published_at` | news-vs-values timing filter | context | `api.player_context.meta` |
| 835 | `news_by_player_key[pk][]` | `{title, headline, tags, category, topic, summary, published_at, published, url, source}` | context | `api.player_context.news_by_player_key` |
| 839 | `adjustments_by_player_key[pk][]` | `{kind, status, injury, date, weeks_out_range, weeks_out, skip_form, beneficiary_review, note, source, consumed}` | context | `api.player_context.adjustments_by_player_key` |
| 189 | `adjustmentInputs.schema` | must equal `"trade-value-adjustment-inputs-v1"` | metadata | `api.product_snapshot.adjustment_schema` |
| 216-228 | `inputs.sources[rawKey].{status, cells[]}` | cells: `{position, tier, alpha, beta}` | data | `api.player_values.sources[<k>].adjustment_cells` |
| 251 | `window.TradeValueTwoTierLive.liveCells()` | live refit cells override | data | `api.player_values` (live override) |
| 66-74 | selector state | `scoring="full"`, `teams=12`, `rosterShape={QB:1,RB:2,WR:2,TE:1,FLEX:2,BENCH:6}`, `benchShare=0.15`, `compareSource="espn"`, `sort`, `filters`, `columns` | selector-config | `api.product_options` |
| 71 | `state.combos[key] = comboKeyFor(key)` | `ValueModel.sourceComboKey(key, scoring, teams, 1)` (qb1 hardcoded) | computation | none-legacy (internal) |
| 205 | `referenceSource = "usatoday"` initial | mirrors `window.TradeValueReferenceSource` | selector-config | `api.product_options` |
| 121 | `window.TRADE_VALUE_TODAY` | date override | context | none-legacy |
| 1208 | `window.TradeValueComparisonControls` (write) | `{refresh, setLockOrder, applyShared}` | selector-config (out) | none-legacy (sibling contract) |
| 1259-1261 | events `trade-value-shared-change`, `trade-value-lock-order-change`, `trade-value-reference-source-change` | cross-widget sync | selector-config | `api.product_options` |
| 1316 | `setInterval(..., 2000)` poll of `window.TradeValueSharedState` | sync safety net | selector-config | none-legacy |

Module constants: `POSITIONS=[QB,RB,WR,TE]` (4), `SOURCE_KEYS` (14), `PURE_VORP_KEYS=[espn_vorp,cbsros_vorp,razzball_vorp]`
with `VORP_SOURCE_DEFS` ppgFields `{espn_ppg, cbsros_ppg, rz_ppg}`, `WEEKED_SOURCE_KEYS` (10),
`LABELS`/`TIPS` display maps, `DEFAULT_BENCH_SHARE=0.15` (23), `FIELD_COLUMNS`.

### 2.3 `value-model.js` (508 lines — pure module, zero I/O)

No fetch, no DOM, no storage, no window reads. Exports `globalThis.ValueModel` (506).
Every input arrives as a function parameter from the two widgets above.

| function (file:line) | inputs | outputs |
|---|---|---|
| `sourceComboKey` (27-39) | `source, scoring, teams, qbSlots` | combo key string or null |
| `flexEligible` (41-45) | `shape` | position array (SUPERFLEX prepends QB) |
| `stableTiebreak` (49-53) | `a, b` (`name`, `player_key`) | comparator number |
| `roleMap` (57-89) | `values` Map, `playerOf`, `teams`, `shape` | `Map<playerKey, "starter"\|"bench">` |
| `sharedPieBasis` (96-113) | `values, anchor, playerOf` | `{keys, target}` or null (needs ≥40 shared) |
| `benchShareOf` (125-138) | `values, roles` | share in [0,1] or null |
| `scaleToSharedTotal` (148-165) | `values, anchor, playerOf` | scaled Map |
| `shapeToAnchorPeaksThenSharedTotal` (171-206) | `values, anchor, playerOf` | per-position peak-scaled Map |
| `normalizeToFixedPie` (209-257) | `values, share, roles, anchor, playerOf, singleScale, fallbackTarget` | normalized Map |
| `starterMarkupSane` (275-278) | `markup` | bool (band [0.98, 1.6]) |
| `fixedPieDirectionSane` (298-302) | `rawStarterShare, starterShare` | bool |
| `peakAgreement` (319-344) | `anchorPeaks, sources, low, high, labelOf` | `{ok, compared, offenders, band}` (default band [0.80, 1.25]) |
| `projectionRoles` (374-415) | `pool, teams, shape, rankOf` | `{roles, direct, baseline}` |
| `positionalTierScales` (433-457) | `rows, targetFor(pos), share` | `{starter, bench, starterRaw, benchRaw, target}` |
| `allocationCounts` (461-479) | `pool, rankOf, teams, shape` | `{direct, lineup, rostered}` |

Constants: `POSITION_ORDER`, `DEFAULT_FLEX_ELIGIBLE=[RB,WR,TE]`, `MIN_SHARED_FOR_PIE=40`,
`STARTER_MARKUP_SANE_LOW/HIGH`, `PEAK_AGREEMENT_LOW/HIGH`, `STARTER_DIRECTION_EPS`.

### 2.4 `index.html` inline IIFEs

**Methodology renderer (1884-2220)** reads: `methodology-data` blob
(`default_combo` (1904), `bench_share` (1952, 2067), `combos[<key>]` (1959, 1972),
per-source `default_weights` (2066), `position_shares`, `adjustments[<src>].{movers, players}`);
`window.TradeValueSharedState` (1958, 1971, 1991, 2045, 2114, 2122);
`window.TradeValueTwoTierLive` (2069); listens `trade-value-shared-change` (2217).
Category: context/metadata → `api.player_context` + `api.product_options`.

**Data-health renderer (2222-2307)** reads: `players-data` meta
(`dataset_status.ui_hint.start_collapsed` (2246), `players.length` (2259));
fetches `comparison-sources-data.json` (throws on `!ok` → "Dataset health unavailable"),
`player-news.json` (`.catch(() => null)`), `reference-freshness.json` (`.catch(() => null)`).
Category: health → `api.product_snapshot.health`.

---

## 3. Schema inventory of the JSON artifacts

### 3.1 `comparison-sources-data.json` (2.7MB, 80k lines; `built_at` 2026-10-02)

Top-level keys: `built_at`, `display` (lower-cased key → display name, 600+ entries),
`espn_zeroed` (4 int player-key IDs), `player_keys` (lower-cased name → int, ~600),
`source_validation` (source → `"live"`/`"stale"`), `sources` (14 sections), `teams`
(key → NFL abbrev), `value_weeks` (`{ecr, espn, monday, pm, rz}` → week int or null).

`sources` keys: `cbs, cbs_adjusted, cbsros, ecr, espn, espn_implied, fantasycalc,
fantasycalc_adjusted, fantasypros, fantasypros_adjusted, prediction_markets, razzball,
usatoday, usatoday_adjusted`.

Common per-source metadata: `name, kind, claimed_settings, position_coverage, native_unit,
update_cadence, value_provenance ("published"|"modeled"|"mixed"), week_designated, published,
content_vintage, fetched_at, promoted_at, promoted_from_review, promotion_note,
provenance_note, url, reindex_anchor (always "espn_leg"), fit_bake_id (adjusted only),
source_provenance.{...}, combos`.
ESPN extras: `espn_priced_pids[]`, `espn_snapshot`, `espn_status{reason,stale,vintage}`, `rails`.
cbsros/espn extras: `method, method_group ("ddf-methodology"), provenance, source_url, vintage`.

`combos`: keys `<scoring>_<teams>[_qb1]` where scoring ∈ {non, half, full}, teams ∈ {10, 12}.
Per combo: `n`, `native` (player_key → raw upstream value), `reindexed` (player_key → 0-70 scale),
`index_total.<pos>.{factor, n_priced, pre_total, target_total}`,
`fit` (Shape A `flex_aware_pie.buckets["<pos>/<slot>"]` for CBS-style, or Shape B per-position
`{anchor, method:"isotonic_pava", n_pairs, native_min, native_max}` for FantasyCalc-style).

Grain: `(source_key) × (combo = scoring × teams × qb_mode) × (player_key)` → value.

### 3.2 `player-news.json` (~289KB; `meta.schema = "player-news-v2"`)

Top-level: `meta`, `adjustments_by_player_key` (`"<pk>" → [adjustment]`, 16 keys),
`news_by_player_key` (`"<pk>" → [news]`, 544 matched), `checked_but_not_adjusted` (4 review records).

Adjustment fields: `id, player, player_key, team, kind ("injury" only observed), injury,
status (Out/Doubtful/Questionable/IR/PUP/Out (protocol)/IR (season-ending...)),
weeks_out, weeks_out_range ([int,int] or null), date, note, source, skip_form,
consumed, consumed_at, beneficiaries (always []), beneficiary_review`.
News fields: `player, player_key, title (HTML-entity-encoded), summary (always ""),
url, source, source_reliability ("standard"), published_at, tags (injury/role/[])`.
Review fields: `asof, date_checked, player, disposition (already-priced/monitoring/not-material),
original_disposition?, summary, reason`.
`meta`: `schema, generated_at, injury_data_updated_at, source_refresh_at,
trade_values_published_at, latest_actionable_news_at, feeds[4], fetched/raw/matched/
unmatched/value/suppressed/review/invalid/adjustment/checked_but_not_adjusted counts,
review_suppression_counts, note`.

Join key: integer `player_key` (dict key, mirrored on each record). `player` string is
display-only (fragile: punctuation/Jr./suffixes). Team-level buckets exist (`106`=Jets,
`108`=Bills) with no distinguishing flag. No explicit expiry flag — freshness from
`date`/`published_at`/`weeks_out`/`consumed`.

### 3.3 `adjustment-inputs.json` (~34KB; `schema = "trade-value-adjustment-inputs-v1"`)

Top-level: `schema, version (= bake id, e.g. ddf-20261003-espn-ppr-12t-0p15), status ("live"),
generated_at, fit, sources (7: cbs, cbsros, espn, fantasycalc, fantasypros, razzball, usatoday),
stage2_cell_format (field legend), summary, review_rows (3 unresolved-identity rows)`.

`fit`: `scoring ("ppr"), teams (12), bench_share (0.15), role_config.{teams, roster:{QB,RB,WR,TE,FLEX,BENCH}, note},
reference_combos (per-source combo), espn_snapshot_date, pie_vintage, ddf_leg_bake_id,
ddf_leg_path, ddf_leg_sha256, pie_source, fixture, fixture_players, fixture_built_at (null),
combo_note, espn_purity_note`.
`sources.<name>.cells[]` (8 per source = 4 pos × 2 tiers): `{source, position, tier (starter|bench),
alpha, beta, n, x_mean, y_mean, fallback? ("identity" when degenerate)}`.
`sources.<name>.diagnostics["POS|tier"]`: `{cell, alpha, beta, x_mean, y_mean, n_pairs,
fallback ("identity"|false), reason (fewer_than_5_pairs/non_positive_slope/null)}`.
Wrapper: `n_published, reference_combo, role_counts{starter,bench}, status ("live")`.

**Source-level, not player-level** — no per-player join field. Tiers apply by (position, role)
under whatever roster shape is active at render time.

### 3.4 `players.json` fixture → `players-data` inline island

Fixture `data/fixtures/current/players.json`: `{meta, players}` — meta carries snapshot dates
(`as_of`, `ecr_snapshot`, `ecr_content_date`, `espn_snapshot`, `pm_snapshot`, `rz_snapshot`),
`n_players` (610), `n_k` (45), `n_dst` (32), `dataset_status`, per-position shade baselines,
method notes. Player: `player_key` (number), `name`, `pos`, `team`, ECR leg
(`ecr_ros/ecr_ppg` per-scoring), ESPN leg (`espn_ros/espn_ppg/...`), PM leg, Razzball leg,
`pricing` (experts_only|espn_only), `games_remaining`, `blend_ros`, `blend_ppg`.

Frontend requires only: `player_key`, `full_name`‖`name`, `pos` (must be in QB/RB/WR/TE),
`team`, optional `espn_ppg`/`rz_ppg`/`cbsros_ppg` per-scoring maps. Fixture has `name` only
(no `full_name`) — the `full_name` branch never fires today. K/DST are baked in the fixture
but silently dropped by both widgets' position filters.

`assets/reference-freshness.json` pins SHA-256 hashes of the four shipped JSONs
(comparison-sources-data, player-news, players, source-import-health); all `enforced: false`.

---

## 4. Calculations inventory (browser-side economics)

### 4.1 `value-model.js` — shared pure functions (methodology-adjacent)

`roleMap` (starter/bench/waiver assignment by slots), `sharedPieBasis` (values∩anchor,
≥40 overlap), `benchShareOf` (measured share — the docstring explicitly rejects a hardcoded
0.15), `scaleToSharedTotal`, `shapeToAnchorPeaksThenSharedTotal` (per-position peak fit),
`normalizeToFixedPie` (**`singleScale` branch**: as-published sources take one global scale
preserving cross-position rank; ESPN DDF takes the two-tier starter/bench split),
`projectionRoles` (superflex uses surplus-over-baseline for flex; standard uses raw rank),
`positionalTierScales` (ESPN-leg per-position two-tier solve), `peakAgreement` (cross-source
curve-shape check, default band [0.80, 1.25]), `allocationCounts`, `stableTiebreak`,
`sourceComboKey` (fantasycalc-family gets `_qb1`/`_qb2` suffix; others drop qbSlots),
`flexEligible`, `starterMarkupSane` ([0.98, 1.6]), `fixedPieDirectionSane`.

### 4.2 `curve-widget.js` — the heaviest economic surface

- **`TwoTier` module (lines 195-584):** browser port of `pipelines/build_ddf_two_tier_leg.py` —
  `softplus`, `sliceExposures`, `solveTierPrices` (closed-form 2×2 per position), `feasibleAt`,
  `feasibleBenchShareInterval` (bisection), `sliderBounds`, `roundHalfEven` (matches Python
  `round()`), `displayValue`, `normalizeThenRound`, `tailFloor`, `benchMixFor`,
  `buildPositionTiers` (tier partition), `calibratePosition` / `calibratePositionFeasible`,
  `priceForProjection`, `skillBenchShares`, `legacyBenchMixFor` (round-half-up of
  `LEGACY_BENCH_MIX_12={QB:10,RB:27,WR:33,TE:10}` by teams/12 — the live path; dynamic
  `benchMixFor` exists but is dead in the widget).
- **`refitLiveCells()` (1991-2041):** the OLS refit — per (source, position, tier) over DDF's
  own tier partition, requires ≥2 pairs and positive var(x); `beta=sxy/sxx`, `alpha=meanY-beta·meanX`.
- **`buildLiveAdjustedMap` (1436-1494):** applies cells as `max(0, alpha + beta·value)`; DDF-native
  sources (espn/cbsros/razzball) are **fail-closed on missing cell** (player withheld); non-DDF
  fall back to raw value.
- **`buildVorpRows` (1117-1255):** raw-VORP economics — waiver line = first waiver-tier player by
  PPG (fallback: last), `rawProjectionVorp = max(0, ppg − waiverLine)`, scales
  `rawScale/targetTotal/starterScale/benchScale` off `espnTargetTotal` sums; populates `espnRoleByKey`.
- **`ddfTwoTierValues` (1867-1885)** / **`ddfTwoTierValuesForSource` (1899-1968):** full-precision
  two-tier values, scaled by `70/max(raw)`; rounding is display-only, never enters OLS.
- **`twoTierConfig` (1781-1837)** / **`twoTierCalibration` (1839-1861):** cached per
  `${scoring}|${teams}` and `${cfgKey}@${share}#${pieSig}`; per-position feasible-share bounds
  fixed at `[0.01, 0.30]`; fail-closed via `entry.error`.
- **Pie targets:** `espnTargetTotal` (953-968) prefers live `twoTierConfig().pies[pos]`, falls back
  to fixture `index_total[pos].target_total`; `commonFixedPieTotal` (977-985) is the **median**
  (not sum) across source totals — the fallback when live pies are unavailable.
- **`rebuildDomain` (1532-1598):** orchestrates everything — ESPN anchor (live cells or built leg),
  `displayShare = anchorDisplayShare(anchorMap)` (measured via `benchShareOf`, fallback
  `DISPLAY_BENCH_SHARE=0.15`), per-source dispatch (`_adjusted`/two-tier-native →
  `normalizedAdjustedMapFor`; as-published → `buildSourceMap`; else fixed-pie normalize),
  pure VORP → `ValueModel.scaleToSharedTotal`.
- **`runRegressionGuards` (3393-3493):** 12 blocking checks
  (`sourceMapCoverage, sourceToggles, noAggregate, stableDomain, validValues,
  distinctSourcePeaks, valuesAboveCollapseFloor, dynamicAxisCoversData, sharedPlayerAxis,
  rosterTransitions, fixedPieIndexed, defaultGroupedSources, pureVorpAvailable,
  adjustableBenchShare, tieredEspnValues`); any failure → `guardsPassed=false` → `draw()` refused.
  Writes frozen `window.TradeValueCurveDiagnostics`.
- **`fixedPieDiagnostics` (2974-3048):** per-source pie checks; as-published marked
  `basis:"pipeline"` (always ok); ESPN special-cased to summed `espnTargetTotal`.
- `applyRosterShape` (1340-1378): pass-through for as-published + pure-VORP + default shape;
  else per-position ratio clamped to **[0.25, 1.8]**, then fixed-pie rescale over skill positions.
- `buildCbsAdjustedMap` (1380-1409): averages per-player `_adjusted/raw` multipliers from
  fantasycalc/usatoday/fantasypros against CBS direct; rescales per position to
  `index_total[pos].target_total`.

### 4.3 `comparison-dashboard.js` — table-side economics

- **`buildVorpRows` (521-592):** same raw-VORP economics as the widget (roles via
  `ValueModel.projectionRoles`, waiver baseline, `pure`/`adjusted` splits).
- **`buildLiveAdjustedMap` (265-286):** `max(0, alpha + beta·value)` per player.
- **`buildCbsAdjustedMap` (648-677):** CBS × mean(adjusted/raw ratios).
- **`normalizeTradeChartToFixedPie` (487-497)** → `ValueModel.normalizeToFixedPie` with
  `fallbackTarget=commonFixedPieTotal`.
- **`normalizedAdjustedMapFor` (423-434):** cells → `ValueModel.shapeToAnchorPeaksThenSharedTotal`,
  else fixed-pie normalize.
- **`rebuildSourceMaps` (679-703):** per-source dispatch incl. `cbs_adjusted → buildCbsAdjustedMap`.
- **Week/freshness math:** `weekForSource` (98-109: `fit_bake_id` → `week_designated` →
  `value_weeks.monday` fallback chain), `rolloverDate` (next Monday after `built_at`),
  `activeReferenceWeek`, `isWeekCurrent`, `sourceIsStale`.
- **News/context:** `normalizeNewsEntry` (768-803: keyword filters, "fresher than values" timing
  vs `tradePublishedAt`), `normalizeAdjustmentEntry` (805-832), `playerContext` merge + sort.
- **Import/export:** `exportState` (versioned snapshot → Blob download), `applyImport`
  (validates scoring ∈ {standard,half,full}, teams ∈ {8,10,12,14}, benchShare ∈ [0,0.5]).
- **Note:** `buildEspnIndexedMap` is declared twice (604 and 630); the second declaration wins
  via hoisting, making the fixture-leg path (604-614) unreachable.

### 4.4 `index.html` inline renderers

- Methodology renderer: reads `methodology-data.combos`, renders pies/movers/players;
  `currentWeights` falls back to per-source `default_weights`; `bench_share` rendered as %.
- Health renderer: reads `players-data` meta + the 3 fetched JSONs; renders health cards.
- No economic math beyond display formatting (largest-remainder rounding lives in the widget:
  `pieDisplayTenths`, curve-widget.js:2188-2200).

---

## 5. Source-specific branches

| group | keys | distinct behavior |
|---|---|---|
| `AS_PUBLISHED_KEYS` | usatoday, fantasycalc, fantasypros, cbs | `singleScale: true` (global scale preserves cross-position rank); `applyRosterShape` pass-through; lock-order uses `nativeSourceMaps`; diagnostics `basis:"pipeline"` always ok |
| `ADJUSTED_INDEXED_KEYS` | fantasycalc_adjusted, usatoday_adjusted, fantasypros_adjusted, cbs_adjusted | 8-cell completeness gate; paused unless complete (espn exempt); `rawKeyForAdjusted` (`cbs_adjusted`→`cbs` special case); wider [0.6,1.4] agreement band, warn-not-fail |
| `PURE_VORP_KEYS` | espn_vorp, cbsros_vorp, razzball_vorp | pure value-above-waivers; `comboKey` → null; `VORP_SOURCE_DEFS` ppgFields `{espn_ppg, cbsros_ppg, rz_ppg}`; scaled via `ValueModel.scaleToSharedTotal` |
| DDF-native two-tier | espn, cbsros, razzball | own two-tier calibrations; **fail-closed on missing live cell** (player withheld) |
| `cbs_adjusted` | special | validation/combos read from `cbs` (not `cbs_adjusted`); own `buildCbsAdjustedMap` factory |
| `espn` as anchor | — | anchor for all fixed-pie scaling; `displayShare` measured off it; special-cased in diagnostics |
| fantasycalc-family | — | `_qb1`/`_qb2` combo suffixes; always 1-QB basis label |
| superflex | shape flag | QB added to flex eligibility; flex scored by surplus-over-baseline instead of raw rank |
| lock-order `"disagreement"` | — | max−min metric instead of a source column |

---

## 6. Fallback paths (classified)

**Fail-closed (throw / refuse / withhold):**
- `comparison-sources-data.json` fetch `!ok` → throws → "Curves unavailable" (curve-widget.js:707-710)
- canonical identity conflict (`values.get(playerKey) !== value`) → throws `Conflicting canonical identity` (curve-widget.js:1002, 1041)
- empty canonical map → throws "Canonical player records are unavailable." (curve-widget.js:3504, comparison-dashboard.js:1289)
- `data.source_validation[key] !== "live"` for any SOURCE_KEY → throws at init (curve-widget.js:3506)
- `solveTierPrices` degenerate → throws; per-position calibration failure → `invalid: true` (withheld)
- DDF-native missing live cell → player withheld from map (curve-widget.js:1467-1472)
- `positionalTierScales` zero raw/target → scale 0 (value-model.js:450-453)
- `runRegressionGuards` any failure → `guardsPassed=false` → `draw()` refused
- `sharedPieBasis` needs ≥40 shared players (`MIN_SHARED_FOR_PIE`)

**Fail-open (degrade silently):**
- `adjustment-inputs.json` fetch/schema failure → `null` → every `_adjusted` curve paused, chart still renders (curve-widget.js:733-736; comparison-dashboard.js:189-192)
- `player-news.json` fetch failure → empty news object (comparison-dashboard.js:168-169)
- `reference-freshness.json` / `player-news.json` fetch failure in health card → `.catch(() => null)`, card not rendered
- `scaleToSharedTotal` / `shapeToAnchorPeaksThenSharedTotal` with no basis → identity copy of values (value-model.js:151, 176)
- `normalizeToFixedPie` with no basis → `fallbackTarget(start+bench)` or raw total (value-model.js:225-228)
- `espnFixtureLeg().size < 40` → warn + fall back to `buildEspnRows().adjusted` (curve-widget.js:1309-1321)
- missing `player_key`/name/non-skill-position → row silently dropped from canonical map
- `team` missing → `"—"` substituted (row still priced and ranked)
- `full_name || name || ""` chain; empty name → silent drop
- `buildEspnIndexedMap` duplicate declaration — second wins, fixture-leg path unreachable (comparison-dashboard.js:604 vs 630)
- export button: `link.href = blob` coerces Blob to `"[object Blob]"` — export silently does nothing (comparison-dashboard.js:1160-1164) — latent bug, not contract-relevant

---

## 7. Identity and join mechanisms

- Master map: `canonicalByKey: Map<Number(player_key), {player_key, name, pos, team, espn_ppg, rz_ppg?, cbsros_ppg?}>`
  built once per widget from the `players-data` inline island (`curve-widget.js:891-910`,
  `comparison-dashboard.js:311-329`); K/DST filtered by `CHART_POSITIONS=[QB,RB,WR,TE]`.
- Values join: `Number(data.player_keys[sourceId])` → `canonicalByKey.get(playerKey)`
  (curve-widget.js:998, 1037; comparison-dashboard.js:470). Native PPG legs iterate
  `canonicalByKey` directly (`rz_ppg`/`cbsros_ppg`, curve-widget.js:1014-1029).
- News/adjustments join: `news_by_player_key` / `adjustments_by_player_key` keys coerced via
  `Number(key)` (comparison-dashboard.js:1286-1287).
- `value-model.js` joins only via the caller-supplied `playerOf(playerKey)` accessor — no
  name-based resolution inside the model.
- Init gates: both widgets throw if the canonical map is empty.

**Flagged soft spots** (identity must be fail-closed per project rules):
1. `team` `"—"` fallback (curve-widget.js:901, comparison-dashboard.js:324) — a teamless player
   keeps its slot in pies and ranking.
2. Waiver-baseline `?? fallback?.ppg ?? 0` chain (curve-widget.js:1141-1142,
   comparison-dashboard.js:545-546) — with no true waiver player, "above-waivers" is computed
   against the lowest rostered player or zero.
3. `full_name ‖ name ‖ ""` display chain — fail-closed downstream (empty name drops the row),
   but the two labels are never audited for agreement.
4. `news_by_player_key` string→Number coercion is silent; no validation that its key set ⊆
   `canonicalByKey` keys. Team-level buckets (106=Jets, 108=Bills) have no distinguishing flag.
5. `comparison-dashboard.js:1288`: `universeSize = Object.keys(data.player_keys).length` —
   a source-side count, not a player count (double-counts shared players).

---

## 8. Proposed contract-surface mapping (summary)

| current read | proposed JEG-327 surface |
|---|---|
| `comparison-sources-data.json`: `sources[<k>].combos[<c>].{values,reindexed,native,index_total}`, `player_keys` | `api.player_values` |
| `comparison-sources-data.json`: `built_at, value_weeks, source_validation, espn_zeroed`, per-source `{fit_bake_id, week_designated, published, espn_snapshot, fetched_at, vintage, method_group, value_provenance, ...}` | `api.product_snapshot` |
| `players-data` island: `players[]` identity + `espn_ppg/rz_ppg/cbsros_ppg` triplets | `api.players` |
| `player-news.json`: `news_by_player_key`, `adjustments_by_player_key`, `meta`, `checked_but_not_adjusted` | `api.player_context` |
| `adjustment-inputs.json`: `sources[<k>].cells[]` (alpha/beta), schema gate, version | `api.player_values` (cells) + `api.product_snapshot` (schema/version) |
| `methodology-data` island: `combos`, `default_combo`, `bench_share`, `position_shares`, `adjustments` | `api.player_context` (methodology copy) + `api.product_options` (bench_share default, defaults) |
| `reference-freshness.json` | `api.product_snapshot.health` |
| selector state: scoring, teams, rosterShape, benchShare, positionWeights, lockOrder, referenceSource, compareSource, sort, filters, columns | `api.product_options` |
| `value-model.js` pure functions (roleMap, normalizeToFixedPie, ...) | backend-owned reference implementations; FE keeps versioned interaction transforms only (Phase E) |
| `TwoTier` browser port, `refitLiveCells` OLS, `buildVorpRows` economics | must be inventoried into Phase E computation-ownership assignments — **not** to be re-decided here |
| window globals / events / DOM controls / CSS | none-legacy (intra-app wiring, not data contract) |

---

## 9. Open questions (consolidated, for the Phase B contract draft)

1. Where do `value-model.js`'s `opts.anchor`, `opts.playerOf`, `opts.share`, `opts.singleScale`,
   `opts.rankOf`, and `targetFor(pos)` originate — backend snapshot fields or caller derivation?
   (`share` is the methodology-adjacent bench-share knob; `singleScale` is the per-source
   one-tier/two-tier switch; `rankOf` drives roster allocation.)
2. `MIN_SHARED_FOR_PIE = 40` — why 40? Contract guarantee or defensive constant?
3. `STARTER_MARKUP_SANE_*` [0.98, 1.6], `PEAK_AGREEMENT_*` [0.80, 1.25] — version-pinned
   contract values or client heuristic knobs?
4. Should the `players-data` and `methodology-data` islands stay inline in `index.html` or become
   versioned sibling assets (`players.v<n>.json`)? Today the only version pin is the
   `reference-freshness.json` SHA (unenforced) plus the `?v=` build tag on JS only.
5. `commonFixedPieTotal` uses the **median** across source totals as the fallback pie — confirm
   this matches the pipeline's pie identity.
6. `buildEspnIndexedMap` duplicate declaration (comparison-dashboard.js:604 vs 630) — intentional?
   The fixture-leg path is currently unreachable.
7. `comboKeyFor` hardcodes qb-count `1` (`ValueModel.sourceComboKey(key, scoring, teams, 1)`) —
   correct for all 12 combos or only FantasyCalc?
8. `data.player_keys` vs fixture `player_key` typing — which side of the boundary owns the
   number-vs-string contract?
9. `full_name` vs `name` — which is canonical? The build should define it; the frontend should
   pin to one (drop the `‖` chain).
10. K/DST: baked in the fixture (45 K, 32 DST), hidden by both widgets. Does the boundary ship
    them or keep filtering at the frontend?
11. `weeks_out_range` is `[int,int]` or `null`; `consumed_at` null-when-false; `beneficiaries`
    always `[]`; `status` strings are prose, not an enum — the FE contract should pin canonical
    sets for all of these.
12. `adjustment-inputs.json` `fallback` key-presence asymmetry (`cells` omits the key when normal;
    `diagnostics` always present) — consumers must handle presence, not just type.
13. `pie_source` ships a CI absolute path (`/home/runner/work/...`) into the browser bundle —
    strip before publish or document.
14. News `url` fields (~280): confirm the UI renders them as read-more links (else dead data
    that needn't enter the contract).
15. `window.TradeValueLockOrder` read+write across widgets; `window.TRADE_VALUE_TODAY` setter
    unknown — document the cross-widget contract explicitly in Phase B.
16. Dead/retired UI to not mistake for contract: `#valueModeSeg` (always "indexed", element
    removed), dynamic `benchMixFor` (dead; only `legacyBenchMixFor` runs), `#valueModeSeg`.

---

## Appendix — worker reports

Raw per-file reports (with `<think>` planning stripped in this synthesis where present):

- `lanes/inbox/minimax/JEG-327-inventory-curve-widget.json` — curve-widget.js (3564 lines)
- `lanes/inbox/minimax/JEG-327-inventory-comparison-dashboard.json` — comparison-dashboard.js (1330 lines)
- `lanes/inbox/minimax/JEG-327-inventory-value-model.json` — value-model.js (508 lines)
- `lanes/inbox/minimax/JEG-327-inventory-index-html.json` — index.html (2328 lines, 1.4MB)
- `lanes/inbox/minimax/JEG-327-inventory-sources-data.json` — comparison-sources-data.json schema
- `lanes/inbox/minimax/JEG-327-inventory-news-adjustments.json` — player-news.json + adjustment-inputs.json schemas
- `lanes/inbox/minimax/JEG-327-inventory-players-identity.json` — identity artifact + join mechanisms
- `lanes/inbox/minimax/JEG-327-inventory-sweep.json` — full-tree load sweep (completeness backstop)

**Key cross-check:** the sweep worker confirmed the 8 required inputs are necessary but not
sufficient — the complete frontend data-load set is 11 paths (8 + `reference-freshness.json` +
`methodology-data` island + 3 CSS files for asset versioning), plus Google Fonts (external,
cosmetic). No `players-data.json` exists on disk; the identity artifact is inline-only.
