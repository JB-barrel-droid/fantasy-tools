## 2026-10-31 - Methodology worked example generated from the fixture (JEG-1397, finding J1393-04)

Contract: make `docs/methodology.md`'s "Worked example" and "Hand-check one value" reproduce from
`tests/fixtures/value_pipeline_worked_example.json` again, and keep them that way. Docs, a generator and a
test only: no engine, reference, fixture or value change.

### Verified (check named)
- The old text did not reproduce. Running the fixture through `pipelines/spec_reference` gives, for `p1` RB
  Delta, starter line 12 (doc: 10), waiver line 9.357143 (doc: 7), DDF Value 52.165616 (doc: 48.511113),
  DDF Value (projections) 48.084613 (doc: 45.086821); `c5` Indexed factor 0.525453 (doc: 0.519241); RB Juliet
  DDF Value 0 and DDF Value (projections) 0, low confidence (doc: 0.785708 and 3.054707). Bench seats are
  QB 1 / RB 1 / WR 1 / TE 1 (doc: RB 2 / WR 2). Checked by hand-running `spec_reference.worked_example.run_fixture`.
- The engine (`node tests/value_pipeline_driver.js app/trade-value-chart/assets/value-model.js <fixture>`, plus
  `--variant variant_expected_starts`) and `pipelines/value_reference.run_pipeline` give the same RB Delta lines,
  DDF Value, DDF Value (projections), `c5` factor and RB Juliet values (printed side by side, equal to about 1e-14).
- `python3 tools/methodology_worked_example.py` writes the section between `BEGIN/END generated worked example`
  markers: the legacy slices mode (labelled legacy), its hand-check, and a current expected-starts example and
  hand-check from the fixture's `variant_expected_starts` (bench 5, round lineup parameters). Every number is
  read from the spec reference's result; the bench-seat scores it prints are checked against the convention's
  own seat order and the generator stops if they disagree.
- `python3 -m unittest tests.test_methodology_worked_example`: 6 tests, OK on this branch; on main's
  `docs/methodology.md` 4 fail (no markers, stale 48.511113, VP-2.5 still the first-non-starter rule).
  Wired into `test-unit-modules` beside `tests.test_methodology_consistency` (a doc check, so not in the
  `test-core` deploy gate); `tests.test_run_suite` and `tests.test_validate_shards` pass.
- VP-2.2d (greedy bench fill, JEG-1121), VP-2.5 (midpoint starter line), the VP-2.6 slice wording, ES-2 and
  ES-3 now match `pipelines/lib/roster_convention.py` (`vorp_bench_allocate`, `starter_line`) and the engine's
  `vpAllocate` / per-source step in `runValuePipeline` (read side by side).
- Still green after the doc change: `tests.test_spec_reference_value_pipeline`, `tests.test_value_pipeline_engine`,
  `tests.test_value_reference_worked_example`, `tests.test_spec_reference`, `tests.test_waiver_band_line`,
  `tests.test_methodology_consistency`, `tests.test_methodology_payload`, `tests.test_doc_staleness`.

### Claimed, not confirmed
- `tests.test_basis_overrides` (20 failures), `tests.test_expected_starts_model` (needs `output/`) and
  `tests.test_week_history` (needs Playwright) fail in this cloud checkout on main too; not caused by this
  change, not investigated.
- The step-to-code table at the top of `docs/methodology.md` (checked at a66f3f40) and the "Publisher Flex
  Allocation" section still describe D'Hondt bench seats as history; left as written.
