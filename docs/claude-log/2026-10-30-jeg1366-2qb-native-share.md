## 2026-10-30 - JEG-1366: 2QB leagues take the QB share from their own replacement level

Contract: in a league with 2+ dedicated QB slots and no superflex slot, the QB share of the pie comes from the league's own points above the 2-QB replacement level (the included projections' QB weights at the league's own lines), not the charts' superflex-market mixes. RB/WR/TE keep their relative shares; within QB each chart keeps its own list (Jeremy 2026-10-30 23:36 UTC, pick A on the before/after on JEG-1366: "Build and merge it as proposed").

### Verified (check named)
- One rule on three paths: `ValueModel.usesTwoQbNativeShare`, `value_reference.uses_two_qb_native_share`, `spec_reference.value_pipeline.two_qb_native_share` (`tests/test_jeg1366_two_qb_native_share.py Rule`).
- Reference: at every scoring x 8/10/12/14 teams with QB 2, the QB weight equals the projections' mean QB weight and W sums to 1; RB/WR/TE ratios unchanged; 1-QB and superflex ppr/12 DDF Values identical with the rule on or off (`ReferenceWeights`).
- Spec reference VP-4 on a hand-made priced dict, computed and fixed bench share (`SpecWeights`).
- Engine (edge runner on a fresh `make sync` build) equals the reference at ppr/12/QB2 within 0.06 (`Engine`).
- 9 of 10 new tests fail on origin/main 7358589c (sources stashed, same test file); the engine parity test passes on both.
- Reference values equal the before/after posted to JEG-1366 at all 9 settings (max difference 0).
- Unchanged suites pass: test_spec_reference_value_pipeline, test_value_pipeline_engine, test_two_qb_direction, test_superflex, test_superflex_publisher_values, test_jeg1365_two_qb_superflex_values, test_value_reference_worked_example (0 mismatches), test_endpoint_parity, test_value_check, test_fractional_seats, test_promotion_model_parity. `pipelines/check_rank_guard.py`: 0 inversions.

### Claimed, not confirmed
- `value_check compare --rerun-engine` and the page at QB 2 need Playwright, which this cloud session lacks; they run in CI.
- The connector changes once Pages serves the new `value-model.js` (get-values loads it from the site); no edge redeploy is needed for the values, but none was checked live.
