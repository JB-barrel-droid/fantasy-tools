## 2026-10-19 - JEG-726 amber fidelity holds never hide from DDF Value

- Policy change: amber fidelity holds (merely lagging: stored_vs_chart value-only drift, publisher_vs_stored with 0 value mismatches and <=2 unresolved names) now produce an amber-level hold that labels the source on the page but does NOT hide it from DDF Value or projection ordering. Red holds keep hiding.
- Root cause of the original bug: all three projections (ESPN, CBS ROS, Razzball) could be held simultaneously by amber-severity conditions (value-only drift, unresolved names), making bench-share None and removing DDF Value from the page.
- Implementation: `hold_decision` in fidelity_pulse.py now detects merely-lagging amber stages and returns holds with `hold_level: "amber"`. `apply_fidelity_holds` passes `hold_level` through to `validationHold`. curve-widget.js reads `hold_level` and treats amber holds as eligible (not hidden).
- Verified: 50 tests pass in test_fidelity_hold.py (including 12 new tests). Negative-tested: all three projections amber-held => hold_level is "amber" on all three; red hold => hold_level is "red". The test_column_swap_red failure in test_fidelity_pulse.py is pre-existing (fails on origin/main too).
- Updated assertions in 2 existing tests that previously asserted `hold is None` for merely-lagging conditions; these now correctly assert `hold_level == "amber"`. The assertion was wrong because the semantics changed: amber holds are now produced but don't hide.
- Not run: full `make validate` sweep (not needed for this policy-only change).
