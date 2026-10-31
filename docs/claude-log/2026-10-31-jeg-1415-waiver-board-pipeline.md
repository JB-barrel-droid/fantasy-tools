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

### Review corrections (JEG-1426) and a stale producer golden (JEG-1427)

The independent review of head 16b8701 asked for changes. Each finding, acknowledged and fixed on the same branch:

1. Served week: `--from-reference` now takes the content week from the reference's prior pair (`currentWeek`,
   `priorWeek`), falling back to the charts' reference week without history; it no longer uses the build day's
   calendar week. Test: built on 2026-11-06 the snapshot is still week 8 and DDF Value stays enabled.
2. The validator re-derives the enable rules (season, later week, current weekly legs, DDF Value current or one week
   behind, prior only with DDF Value, freshness null exactly when unavailable, stale or previous-season never
   published, only the five board sources enabled, feeds match).
3. A weekly file with no status or bye leg gives an unavailable, disabled source instead of a KeyError.
4. Row checks: change = DDF Value minus prior, change needs both sides, on_bye consistent and boolean, bye_week range,
   field types, non-empty reasons, a disabled source's own reason, and header types (inputs, built_at, producer,
   superflex).
5. Tests: 84 now (was 39). Priced 0.0 above unpriced with a lower key, stale and one-week-behind status, unknown-age
   points, stale values label, a week-9 bye board, 28 validator negatives, read-back against get-values' own pipeline,
   off-week build day.
6. `inputs.values.sha256` hashes the exact bytes `--values-out` writes.

JEG-1427: `tests.test_build_weekly_inputs` failed three tests on main because #1211 changed
`data/inputs/player_aliases.json` and the producer golden still pinned the old hash. Only that hash line changed; the
board golden, which records the weekly file's hash, was regenerated with it.

#### Verified (check named)
- `python3 -m unittest tests.test_build_waiver_board tests.test_timestamps tests.test_build_weekly_inputs`: all pass.
- On the old builder and validator (HEAD's files, new tests), 29 of the new tests fail; on the new files all pass.
- `FromReference.test_matches_get_values_at_12_team_half_ppr`: snapshot week 8 and prior week 7 match get-values'
  week view and prior pair; all 741 current and 738 prior DDF Values agree to 1e-6 (max difference about 3e-14).

#### Claimed, not confirmed
- Full CI (preview, v2-render) runs only once the PR leaves draft.
- Pre-existing on main, not touched here: tests.test_weekly_inputs_contract pins a freshness word that
  check_reference_freshness.py no longer has (filed JEG-1428; nightly full suite only).

### Delta review of ff05912: changes needed, fixed
- Medium: the validator took DDF Value's claimed freshness on trust (week 3 on a week-8 board passed as current). It now
  re-derives it from the weeks (the prior pair takes DDF Value's), with a test pinning the rule to the contract's.
- Snapshot labels: a snapshot may carry only published, modeled or stale; the board derives unavailable and
  previous-season, and the validator checks both directions. Empty snapshots from another season or week now build
  valid boards instead of refusing.
- A snapshot with no `source` is refused cleanly (was a KeyError traceback).
- Tests for the four rules the reviewer could delete unnoticed, and the missing-legs CLI test now requires exit 0.
- Verified: 147 tests across test_build_waiver_board, test_build_weekly_inputs, test_timestamps pass; 8 of the new
  checks fail on ff05912's files.
