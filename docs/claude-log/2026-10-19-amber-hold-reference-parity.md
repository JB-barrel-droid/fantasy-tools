## 2026-10-19 - Amber hold reference parity fix (JEG-726)

PR 704 made amber fidelity holds visible in DDF Value on the JS/engine side
(curve-widget.js: `eligibilityReason` returns null for amber, so the source
stays eligible). But the Python reference (pipelines/value_reference.py) still
added amber-held sources to the `hidden` set, excluding them from DDF blend,
bench-share readout and Indexed basis.

Root cause: `Setting.state()` called `section_hold()` which returns a reason
string and loses the `hold_level`. Any truthy hold went to `hidden`.

### Fix

- Added `section_hold_level(inp, section)` that reads `hold_level` from the
  `validationHold` dict (defaulting to "red" when absent).
- Changed `state()`: an amber hold (`hold_level == "amber"`) makes the source
  eligible but NOT hidden. Only red (or missing-level) holds add to `hidden`.

### Verified (check named)

- `test_bench_share_readout_matches_reference`: 3 passed, 16 subtests passed
- `test_main_table_engine_parity`: 17 passed, 2 subtests passed
- `test_ddf_composite_value`: passed (included in above run)
- `test_value_check`: passed
- `test_seeded_hold_build` (including new `AmberHoldNotHiddenTest`): passed
- `make validate`: exit 0 (all tests green)
- New `AmberHoldNotHiddenTest`: red hold => hidden (confirmed), amber hold =>
  NOT hidden (confirmed), missing hold_level => hidden (confirmed)

### Claimed without confirming

- Chain workflow will pass after merge (dispatched, waiting for result).
- The 12-combo headless sweep was not re-run (no chart changes in this PR).
