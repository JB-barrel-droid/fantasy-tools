## 2026-10-29 - JEG-1227 weekly-input contract, local schema and fixtures (S1 of JEG-1195)

Contract: build the versioned `weekly-inputs` v1 contract from the #1083
readiness packet (section 5) as a local, offline validator with deterministic
positive and negative fixtures, so the S2 producer (JEG-1228) can build against
it. No Supabase, feed, schedule, page or math change.

Added: `pipelines/lib/weekly_inputs_contract.py` (stdlib-only validator and
CLI), `docs/weekly-inputs-contract.md`, `tests/fixtures/weekly_inputs/`
(builder, 11 valid and 37 invalid cases, `expected.json`),
`tests/test_weekly_inputs_contract.py`, one `test-unit-modules` line, one
`docs/README.md` row.

Availability vs freshness (the #1083 review point): two fields. `availability`
complete / partial / unavailable; `freshness` current / one_week_behind /
stale / unknown (check_reference_freshness vocabulary and 0/1/2+ rule), null
exactly when unavailable; `label` keeps the five standing labels.

Aligned with JEG-1228's draft (#1085 head `bf585cc`): status field names follow
the stored Sleeper history; optional `inputs` (name, sha256), `input_report`,
`resolved_by` and `source_ids` are accepted.

### Verified (check named)
- `python3 -m unittest tests.test_weekly_inputs_contract`: 28 tests OK
  (every fixture's exact error and warning codes, byte match with the builder,
  every code exercised and documented, versions, CLI exit codes).
- Failing before: with the module absent the suite errors on import; four
  single-line mutations (no zero-fill check, no ROS horizon check, no
  duplicate-key check, freshness ignored) each fail the suite (4, 4, 2, 2
  failures).
- `tests.test_run_suite tests.test_render_sweep_coverage
  tests.test_render_sweep_shards tests.test_doc_staleness
  tests.test_no_real_clock tests.test_validate_runner`: same 4
  `test_render_sweep_coverage` failures with and without this change (render
  modules unrelated to this PR); the rest pass.

### Claimed, not confirmed
- JEG-1228's producer output will validate; it does not exist yet.
- Preview CI's `make test-unit` runs the new line; not watched at commit time.
