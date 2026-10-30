## 2026-10-29 - JEG-1334 fractional-seat helper (option B, JEG-1286)

Contract: Jeremy picked option B for JEG-1286 ("Go with B", 2026-10-29 21:08
UTC; `docs/decisions.md`). Build the seat-share helper on new files only, in
Python and JS: expected seats from Φ((score − τ)/σ), the decomposition into a
weighted mix of whole allocations, and the flex-times-bench mix. Nothing calls
it yet; the engine and reference wiring is JEG-1335, after #1077 and #1105,
because `value-model.js`, `value_reference.py` and the spec reference are hot
files held by those tickets.

Files: `pipelines/lib/fractional_seats.py`,
`app/trade-value-chart/assets/fractional-seats.js`,
`tests/test_fractional_seats.py`, `tests/fractional_seats_harness.cjs`,
`Makefile` (adds the test to `test-unit-modules`, which does not gate deploys).

### Verified (check named)
- `python3 -m unittest tests.test_fractional_seats`: 10 tests pass (about
  50 s).
- σ = 0 and σ = 1e-7 give exactly one allocation, equal to
  `value_reference.allocate`, on all 12 grid settings plus USO and Charlotte
  (`SigmaZeroIsTodayTest`). The helper's hard bench equals
  `roster_convention.vorp_bench_allocate` on all 14.
- The mix's expected flex seats equal `soft_select` to 1e-9 and its bench
  seats add up to the league's bench (`ExpectedCountsTest`). `decompose`
  keeps the expectation on 500 random cases.
- Continuity, 0.01 PPG scans of one player across a cutoff the hard rule
  flips: the largest mix change per step under σ 0.75 is 0.004 to 0.008 (USO,
  Charlotte and standard/10 flex; Charlotte, standard/10 and PPR/14 bench);
  the hard rule jumps 2.0 at the same crossing. The mutation test asserts the
  hard rule fails the check.
- The JS twin matches Python: Φ to 1e-14 on z from −8 to 8, `decompose` and
  `allocationMix` to 1e-12 on 200 random leagues (same allocations, same order).
- Expected flex seats under σ 0.75 match the research script: standard/10
  8.33 RB / 1.67 WR (research 8.3 / 1.7).

### Claimed, not confirmed
- Values are unchanged everywhere: nothing imports the helper yet, so no
  published number can move. Not checked with `make validate` in this session.
- USO has no one-player bench crossing within 1.5 PPG today (the next bench
  candidates are below the marginal player's own position), so the bench
  continuity scans use Charlotte, standard/10 and PPR/14.
