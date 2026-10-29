Frozen week-history fixture for `tests/test_projection_captures.py::BackfillTests`
(JEG-1242). Hand-written, small, and pinned: the expected backfill rows are
written out literally in the test, so do not edit these files to make a test
pass. A new season week belongs in a new-week test case, not here.

What each file exercises:
- week-2: espn only (one per-format null); weekly `cbs`, `fantasycalc` and
  `usatoday` sections that must never become rows.
- week-3: razzball joins (3-decimal rounding, a whole-null player); empty `cbs`;
  a `cbsros` section with ppg but no captured_at, which must be skipped.
- week-4: cbsros joins as source `cbs`; an espn player with two null formats;
  an unmapped `fantasypros` section.
