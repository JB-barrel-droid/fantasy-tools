# 2026-10-08 · Trade targets on DDF Value, tier follows the series (JEG-455, JEG-456 part 2)

Branch `fe/targets-ddf` (from `fe/ddf`). Design notes: "Trade targets: DDF Value as our value; tier follows
the series" and BE-4 in docs/v2-design-notes.md.

## What changed
- app/v2/targets.js: Our value choices `ddf_value` (default, "DDF Value"), `espn`, `cbsros`, `razzball`; header
  comment updated to Jeremy's decision.
- app/v2/v2.js:
  - Trade targets: DDF Value default; "from N sources" (`row.ddfCount`) under Our value; "—" with the engine's
    reason if a null reaches a row; left-out note lists the engine's reasons; footnote follows the pick; pick
    remembered in `localStorage["ddf.v2.targets"]`; option symbol from `sourceMeta` (★ for DDF Value).
  - One tier helper `tierFor` / `tierText`; every `tierLabel(row.espnRole)` replaced (Player values tooltip, Tier
    column, sub-line, drawer; Trade targets table and cards; Compare player rows; drawer follows the tab that
    opened it).
  - `missingReason`: `row.missingReasons[key]` → `row.ddfReason` → generic; now also used by the chart tooltip,
    drawer hero and matrix, and Compare's player values.
- app/v2/shell.html: subtitle "against our values for your league"; footnote span covers the whole "Our value is …".
- app/v2/v2.css: source-count and tooltip-reason styles.
- app/trade-value-chart/assets/curve-widget.js: read-only accessor `getZonesFor(key, pos)` in
  TradeValueCurveControls (no math change).
- Tests: test_v2_targets, test_v2_targets_render, test_v2_ddf_render extended; test_below_leg_zero_render and
  test_espn_zero_badge_render pick ESPN explicitly (outside the test_v2_* lane; two-line change each, needed
  because the default moved).

## Verified
- tests.test_v2_targets: OK, 10 broken builds caught (incl. default reverted to ESPN, DDF Value dropped).
- tests.test_v2_targets_render: numbers/layout OK; in a dedicated run all 16 broken builds caught (incl. default
  reverted to ESPN, tier from espnRole, source count missing, pick not remembered).
- tests.test_v2_ddf_render: OK incl. the new Player values tier check (DDF Value and one other Rank by), the
  simulated `missingReasons` "—" tooltip and the finite-0 "0.0" check; 11 broken builds caught.
- Every other tests/test_v2_*_render.py, test_launch_front_door, test_espn_zero_badge_render,
  test_below_leg_zero_render and scripts/validate.py (58/58) passed on this branch before the rebase. In the full
  sequential run, panels / share / targets broken-build subtests hit page-load timeouts and ECONNREFUSED under
  machine load (no assertion failures); see the report for the re-runs.
- After rebasing onto origin/main (fe/ddf landed as efaa8a1f): sync, then all 15 tests/test_v2_*_render.py
  suites (incl. the new bench_used and the fixed panels suite), test_launch_front_door, test_v2_targets,
  test_espn_zero_badge_render, test_below_leg_zero_render and test_ddf_composite_value pass;
  scripts/validate.py 60/60 (a first run had one load timeout in test_disagreement_units_render, which then
  passed three times, and the full re-run passed).
- Manual: /v2/#trade-targets at 1440 and 390: DDF Value default, "from 7 sources" under Our value, tiers from
  DDF Value, new subtitle and footnote, no horizontal overflow at 390.

## Claimed (not verified)
- `row.missingReasons` is not shipped by the engine yet; only a simulated row was tested.
- Compare tiers use the All-positions zones over every priced player; not checked by a render test.
