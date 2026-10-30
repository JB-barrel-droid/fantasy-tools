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

## JEG-1267 corrections (review of e2a2a07)

- Unknown provenance no longer passes as trustworthy. A leg with data whose freshness is
  current, one_week_behind or stale, or whose label is published, now needs non-null
  content_season, content_week, content_vintage and captured_at (new code
  `leg.provenance_unknown`). Before, the code passed `nullable=True` unconditionally, so
  these nulls validated clean. Leaving the source unstamped is still valid when freshness is
  unknown and the label isn't published (`valid/unknown_no_provenance.json` is the control).
- A malformed scoring list (`[{}]`, `[[]]`, `["half_ppr", {}]`) now returns `field.type`
  issues instead of raising TypeError from `set(scoring)`. A sweep that replaces every value in
  `valid/complete.json` with ten malformed shapes now pins that validate() never raises.
- Partial, unavailable, and zero-versus-missing semantics are unchanged. The suite now has 35
  tests, 12 valid fixtures and 47 invalid fixtures.
- Producer (#1085 at 86031bbc), run against this validator: its bye leg is current/published
  with null content_vintage and captured_at, so its golden output fails the new rule. That fix
  is the producer's (JEG-1245), coordinated on Linear; the producer was not edited here.

## 2026-10-29 20:10 UTC: built files taken out of the PR

The #1085 reviewer found that commit e2a2a07 had swept 20 generated `dist/` and
`app/trade-value-chart/` files into this branch. Against main they would have reverted about
135,000 lines of CI-built output. Merged `origin/main` in (normal merge, no rebase), then one
commit put the 17 files main has back to main's version and removed the 3 that main doesn't
track (`dist/connect/index.html`, `dist/ddf-skill.zip`, `dist/get-values.openapi.yaml`).
No source, test or fixture changed.

Verified:
- `git diff --shortstat origin/main HEAD`: before, 87 files, +18,846 / -135,482; after,
  67 files, +17,148 / -0, none under `dist/` or `app/`.
- `python3 -m unittest tests.test_weekly_inputs_contract`: 35 tests OK.
- #1085 at f668c874 with this branch's `weekly_inputs_contract.py` dropped in:
  `python3 -m unittest tests.test_build_weekly_inputs`, 50 tests OK, 0 skipped.

Claimed, not confirmed: preview CI on the new head (reported on JEG-1227 once it runs).
