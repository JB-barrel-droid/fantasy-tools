## 2026-10-08 - GAP-MAIN-TABLE-ESPN-DRIFT: main table renders the engine's values

Contract: the main page comparison table must show exactly the engine's values
(TradeValueCurveControls.getRows()/getAllRows(), i.e. the chart) for every
column it shares with the chart, deterministically on every load. Branch
`fix/main-table-drift` from origin/main 9b97f88, pushed, not merged.

### Cause
The table (`comparison-dashboard.js`) re-derived every column with its own copy
of the value math (FIX-004's "one model, two renderers"). Two separate defects:

1. Nondeterminism (load-order race). The table's `adjustmentCellsFor` used the
   chart's live refit cells when `window.TradeValueTwoTierLive` existed and the
   baked adjustment-inputs.json cells otherwise. That global is set at the end
   of the curve widget's init. Whichever of the two scripts finished its async
   load first decided which cells priced the *_adjusted columns, and the table
   never rebuilt afterwards (applyShared only rebuilds when settings differ).
2. Wrong numbers on every load. The table's copy had drifted: a second, later
   `function buildEspnIndexedMap` (the one JS actually runs) re-derived ESPN
   from browser projections instead of the built leg, while the source-level
   guards in test_two_tier_frontend read the first definition; published
   charts were re-normalised (the engine uses them as built); adjusted maps
   used published-value tiers instead of DDF tiers; CBS ROS / Razzball VORP vs
   waivers columns were dropped (canonical players lacked cbsros_ppg/rz_ppg);
   the FLEX filter called an undefined `flexEligiblePositions`.

### What changed
- `comparison-dashboard.js`: all value math deleted. `rebuildSourceMaps` now
  reads `getAllRows()` (values + espnRole), `getSourceInfo()` (a column shows
  when the chart can draw it), and the engine's scoring/teams/roster/bench
  share/view. It runs once the engine reports `isReady()` and on every
  `trade-value-rows-change`; before that the table says "Loading values from
  the chart." applyShared only takes position/lock order; import pushes league
  settings to the engine. The 2-second shared-state polling is gone. Outside
  the Indexed view the published columns carry that view's values (as the
  chart does) and their header badge names the view.
- `curve-widget.js`: `isReady()`, `getState().viewMode/viewTitle`, and a
  `trade-value-rows-change` event at the end of every `rebuildDomain` after
  init has finished. No value code touched.
- Tests: new `tests/test_main_table_engine_parity.py` (added to test-core).
  Pinned assertions changed, because they pinned the duplicate-math design the
  bug came from: test_two_tier_frontend's "both renderers" guards now cover the
  engine only, plus a new guard that the table defines none of the pricing
  functions and reads `getAllRows()`; test_static_export no longer requires
  buildEspnIndexedMap/buildEspnVorpMap/normalizeRosterShape/buildEspnRows in
  the table; test_espn_zero_badge_render drops the table-only mutation (the
  table has no copy of the ESPN-0 rule; the engine mutation covers it).

### Verified (check named)
- Reproduced on the origin/main 3ddf90d build (system Chrome, scratch harness, 10
  identical 12-team PPR loads): Waller FC Adjusted 4.8 on 6 loads, 2.0 on 4
  (engine 1.5 on all); 2292 cells differed across loads; every load had
  100-220 cells per column off the engine; ESPN 3.4 vs engine 0.
- Cause of the split: instrumented the first set of `TradeValueTwoTierLive`
  and `TradeValueComparisonDiagnostics` on 8 loads (3ddf90d), then 12
  scenario loads with server-side delays (9b97f88): table-first loads gave 2.0 / USAT 1.4 / CBS 1.5,
  chart-first loads 4.9 / 3.6 / 3.6, every time.
- Fixed build: 10 loads with random 0-2s server-side delays on nine scripts and
  fixtures, plus the four test scenarios x3: 0 mismatching cells, 514/514
  rows, Waller 1.5 / 1.1 / 1.0 / ESPN 0.0 matching the engine.
- `tests/test_main_table_engine_parity.py`: passes on the branch; its
  discrimination test fails the checks on the origin/main 9b97f88
  comparison-dashboard.js (missing VORP columns, 20 engine-only players,
  ~1900 cells) and on a table without the rebuild listener (never renders on
  table-first loads; stale after a rebuild). Confirmed by printing each
  mutation's failures.
- New source guard (`test_table_reads_the_engine_rows_and_prices_nothing_itself`)
  fails on the origin/main table: all 11 named pricing functions are defined
  there.
- 12-combo sweep (3 scorings x 4 sizes, origin/main 9b97f88 build vs branch
  build, setScoring/setTeams on a fresh load): fixedPieIndexed, fixedPie,
  sourceScaleAgreement, scaleAgreement, sourcePeaks identical in all 12; full
  getAllRows() identical in all 12. Table vs engine mismatches: origin/main
  1434-2148 per combo, branch 0. Cells that change on the table, per combo:
  usatoday 136-216, fantasycalc 139-205, fantasypros 137-181, cbs 118-130,
  cbsros 155-240, razzball 180-269, cbs_adjusted 132-143, fantasycalc_adjusted
  154-209, usatoday_adjusted 152-238, fantasypros_adjusted 148-197, espn
  156-249, espn_vorp 137-221, ESPN tier 27, disagreement 194-302; cbsros_vorp
  and razzball_vorp appear (514 cells each); 20 engine players join the table
  and 7 players only the table's own math priced leave it (501 -> 514 rows).
- sourceScaleAgreement is false in 11 of 12 combos on origin/main and on the
  branch alike (true only at 12-team PPR); not caused or changed here.
- `CHROMIUM_PATH=... make validate`: exit 0 (see commit). Also passing:
  test_espn_zero_badge_render (render tests ran, mutation caught),
  test_disagreement_units_render, test_source_combo_contract,
  test_jeg38_raw_vorp_sources, test_dashboard_column_selection_preserved,
  test_week_for_source_designated, test_product_data_wiring,
  test_public_copy_no_vorp, test_published_views_render,
  test_published_league_settings_render, test_below_leg_zero_render,
  test_v2_targets_render.
- test_razzball_dashboard_render and
  test_razzball_production_followups.SourceDateTest fail identically on
  origin/main and the branch (new row GAP-STALE-DASHBOARD-UNIT-TESTS).

### Claimed, not confirmed
- The VORP vs waivers / Adjusted values view badge on the table header was
  not looked at in a browser; the values follow the engine by construction.
- Export/import of table settings now drives the chart's league controls; not
  exercised headless.
- Not checked on the live site (branch not merged).
