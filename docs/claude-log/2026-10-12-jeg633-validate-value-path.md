# JEG-633: value-path suites in the validate gate

**Date:** 2026-10-12  **Ticket:** JEG-633

## What changed
- `make test-core` now runs `tests.test_spec_reference_value_pipeline` (the suite PR 557 merged red). worked_example, roster_convention_parity and bench_share_readout_matches_reference were already in test-core.
- New target `make value-check-compare` (`value_check compare --rerun-engine --strict`). NOT wired into `validate` yet (see below).

## Finding: value_check compare is red on main (verified)
- Cause: PR 530 (JEG-569 part 2) made the JS engine keep held sources in the pipeline but hidden (out of DDF blend, Indexed basis, bench readout). The Python reference was not wired: `Setting.state()` never sets `hidden` and drops held sources from the included set. Razzball is held now, so compare disagrees and 16 bench-share readout tests fail (QB). It is 530, not pre-existing before 564.
- Also stale after 530: two assertions in `tests.test_value_check` still expect restore-from-last-good and held-not-in-inputs.
- Fix written and verified locally, NOT merged (hold while value lanes are in flight): `2026-10-12-jeg633-held-reference-fix.patch`. With it: compare agree (912864 values), bench-share suite, spec_reference_value_pipeline, ddf_composite, roster_convention_parity, worked_example and test_value_check pass; 13-setting sweep fixedPieIndexed true.
- Wire `value-check-compare` into `validate` once the patch or equivalent lands.

## Negative test (verified)
Changed the reference DDF mean to `total / (n + 0.01)`: `value_check compare --strict` exit 2, `test_value_reference_worked_example` 4 failures. `test_spec_reference_value_pipeline` did NOT catch it (still OK), so it pins less of the blend. Reverted.

## Not verified
Full `make validate` not run (machine load, value lanes in flight).
