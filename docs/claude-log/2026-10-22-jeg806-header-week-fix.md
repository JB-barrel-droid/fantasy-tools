## 2026-10-22 - JEG-806: header week derived from data, not calendar

### What changed

Page headers showed "Week 7" (the NFL calendar week) when all 7 sources
were Week 6. Fixed by switching every display module's reference week
from `current_content_week` (calendar) to `first_load_reference_week`
(the newest week any source has published, capped at the calendar week).

Files changed:
- `app/v2/v2.js`: `refWeek` uses `first_load_reference_week`; added
  `calendarWeek` for the "data through Week N, updating" label; added
  `dataAsOfLabel()` showing "as of Oct 19" from `built_at`.
- `app/trade-value-chart/assets/curve-widget.js`: `activeReferenceWeek()`
  returns `first_load_reference_week`.
- `app/trade-value-chart/assets/comparison-dashboard.js`: same fix.
- `app/trade-value-chart/index.html`: classic "How values work" panel
  uses `first_load_reference_week`.
- `tests/test_source_freshness.py`: `HeaderWeekTest` (4 tests) verifies
  the data week is used, not the calendar week; negative-tested.

### Verified

- `make sync` (build tv-20261022-0237-ffb78fe1)
- `guard-harness --assert-good` and `--simulate espn-anchor --assert-bad`
- `value_check.py compare --rerun-engine --strict`: 837049 values agree
- 26/26 `test_source_freshness.py` (including 4 new HeaderWeekTest)
- 104 core tests passed
- v2 render tests (6 passed, 12 subtests)
- preview workflow tests (20 passed)
- Pre-existing failure: `test_derive_lineup_parameters.py::CommittedData::test_derivation_runs_and_lands_in_range` (bye_share assertion, not related)

### Claimed without confirming

- Live site verification (pending Pages deploy)
- 12-combo headless sweep (not run: chart path unchanged, only label logic touched)
