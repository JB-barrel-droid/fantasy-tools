## 2026-10-31 - JEG-1415 offline waiver-board pipeline (slice 1 of JEG-1196)

Contract: build the waiver board's first offline slice on the JEG-1227 weekly-input contract and the JEG-1228
producer's output: a builder, a schema and validator, fixtures and tests, no UI and no publication. Jeremy's ask via the
main chat, 2026-10-31 00:03 UTC ("We can't launch more items in the cloud?").

### Verified (check named)
- `python3 -m unittest tests.test_build_waiver_board`: 39 tests OK offline (about 3.5 s; the reference class builds dist/
  first, as `make sync` does). Hand-worked rows from the producer's `expected_wk8.json` and the values fixture, every
  disabled-source case (stale, one week behind, missing scoring, unavailable, other season, later week, wrong prior
  week, no prior), both lanes unchanged when only the other lane's input changes, refusals, byte-identical reruns
  against the committed `expected_half_ppr_12.json`, and validator negatives.
- The board passes the reference's numbers through: `FromReference.test_values_are_the_references_adjusted_ddf_value`
  compares every priced player's `ddf_value` with `value_reference.compute(...)["views"]["adj"]` at 12-team Half PPR
  (exact equality), and every Change equals DDF Value minus prior DDF Value.
- Tests catch breakage (temporary mutations, reverted): letting a one-week-behind points leg through fails
  `DisabledSources`; filling a missing point with 0.0 fails 3 tests; adding 0.5 to Change fails 3 tests.
- `tests.test_timestamps` (no raw `fromisoformat`) passes after switching to `parse_iso_timestamp`;
  `tests.test_pipelines_import_standalone`, `tests.test_one_name_resolver`, `tests.test_local_mcp_retired` pass.
- Standard, Half PPR and PPR all build; `--from-reference` at 10-team PPR superflex builds and validates, and its saved
  snapshot rebuilds the same rows (`test_cli_from_reference`).

### Claimed, not confirmed
- No new value math: the builder reads DDF Value and the prior-week pair from `pipelines/value_reference.py` and only
  subtracts them for Change (the same pair the site's risers and fallers use). Nothing user-visible yet.
- The engine and the reference agree (value_check's job, not re-run here).
