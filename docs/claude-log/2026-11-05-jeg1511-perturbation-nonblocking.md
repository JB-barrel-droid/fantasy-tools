## 2026-11-05 - JEG-1511: waiver-band perturbation tests stop blocking publication

Contract: Jeremy, 2026-11-05 10:16 CT, on the Week 9 block: "Just don't let this
test block us at all." Move `tests.test_waiver_band_line.OnePlayerPerturbationTest`
out of the blocking gate (`test-core`, and its shard `test-core-shard-4`) into
`test-unit-modules`, which runs in preview CI and reports without blocking. The
band-math and end-to-end classes of the same module stay in the gate. No test
assertion, tolerance or value math changed; the JEG-1511 known-case set stays as is.

Why the case list was not enough: the chain's live Week 9 inputs breach the bar
for the same player and mechanism at settings the list did not name. Run
42031325359 (main 1b4856e, exemption merged): `half_ppr/10 razzball QB 370 -1.0:
1.037` and `ppr/10 razzball QB 370 -1.0: 1.014` failed; the listed standard/10 case
printed as exempt (1.071). Run 42007081569: standard/10 at 1.072. The values move
with every Razzball re-save, so any exact-case list chases the data.

### Verified (check named)
- `make -n test-core` lists only `BandMathTest` and `EndToEndTest` for this module.
- `tests.test_validate_shards` and `tests.test_run_suite` pass (21 tests): test-core
  and the shards still match line for line; test-unit-modules runs the moved class.
- `BandMathTest` + `EndToEndTest` pass locally (7 tests).

### Claimed, not confirmed
- The next main chain run passes post-rebuild validation and publishes Week 9
  (check: chain status, fixture `as_of`, live `built_at`, rendered page).
- Restore the class to test-core when JEG-1511 lands.
