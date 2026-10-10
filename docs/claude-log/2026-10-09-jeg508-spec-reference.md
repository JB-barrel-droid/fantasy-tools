## 2026-10-09 - JEG-508 clean-room spec reference for the source-neutral value pipeline

Contract: write `pipelines/spec_reference/` from docs/methodology.md "Value
Pipeline (source-neutral, 2026-10-09)" only (no reading of
`pipelines/value_reference.py`, `value_check.py` internals, the engine JS, or
the other two JEG-508 branches), reproduce the worked example to 1e-6, and dump
every live value for the lead's three-way diff. Branch `jeg508-specref`, draft
PR, not merged.

### Verified (check named)
- `python3.12 pipelines/spec_reference/worked_example.py`: 4,455 pinned leaves
  of `tests/fixtures/value_pipeline_worked_example.json` (schema /2: every
  `expected` intermediate and output plus `variant_bench_share_0_10`) compared,
  0 mismatches at 1e-6. It matched on the first run except
  `expected.flex_contrast`, which needed the superseded own-value allocation
  added to the adapter.
- `tests/test_spec_reference_value_pipeline.py` (14 tests, added to
  test-unit-modules) fails before the change (ImportError on the origin/main
  tree, run from a scratch copy) and passes after. Its negative tests go red
  on: an expected value perturbed by 2e-6, a variant weight perturbed by 1e-5,
  a missing pinned key, median read as mean, uncapped estimates, bench share
  0.35, and flex by c1's own values.
- `python3.12 pipelines/spec_reference/compare.py pipeline` on the committed
  snapshot (`data/fixtures/current`, built 2026-10-09T22:41:47Z; prior week =
  `data/history/week-4.json`) ran all 13 settings (3 scorings x 8/10/12/14,
  plus PPR 12 SF1) in under a second. At every setting all 7 sources are in
  `I`, and each source's Adjusted total equals the pie. At PPR 12, 520 of 737
  rows have blended DDF 0 and the fill-in adds 84 chart estimates (58 on CBS).
- `make validate` with python3 = /opt/homebrew/bin/python3.12 passed. The
  files that `make sync` regenerated were reverted, not committed.

### Claimed, not confirmed
- The dump agrees with the engine or with `pipelines/value_reference.py`: not
  checked. The lead wires that diff.
- The readings in `pipelines/spec_reference/SPEC_AMBIGUITIES.md` (SA-1..SA-16)
  are literal readings, not Jeremy's or the lead's decisions.
