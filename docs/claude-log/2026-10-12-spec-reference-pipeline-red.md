# 2026-10-12 tests.test_spec_reference_value_pipeline red on main

Root cause (verified by running the suite on origin/main ff705378: 6 failed, and after the fix 47 passed across the spec-reference, value-reference and roster-convention-parity suites):
- JEG-560 (#557) regenerated tests/fixtures/value_pipeline_worked_example.json from the Python reference. That reference writes status "excluded" for any non-included source, so held source c3 flipped from "held" to "excluded". The spec reference (and the spec, methodology worked example: "c3 is held") echoes the input status. Fixture was wrong; fixed expected c3 status back to "held". The Python test only compares included vs not, so it never noticed.
- #557 also updated the Python hand-check (RB Delta p1 Adjusted 49.077706, DDF blended 48.882505) but not the same hand-check in tests/test_spec_reference_value_pipeline.py. Those pins were stale from the deliberate convention change (bench seats, midpoint starter line); the spec reference already produces them, so two independent implementations agree. Updated the two pins.
- Guards: WalkCatchesBreakage tests already prove the leaf walk catches a perturbed value; they were red because of the extra c3 mismatch and are green again. The red run itself showed the walk catches a status change.
Not verified: why make validate / CI did not gate on this suite (not investigated).
