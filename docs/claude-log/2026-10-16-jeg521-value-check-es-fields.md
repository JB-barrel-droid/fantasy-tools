# JEG-521: value_check expected-starts parity (2026-10-16)

## What

Extended value_check to compare expected-starts fields (lineupShare,
startWorthy, ddfTier) and the JEG-571 playerTag between the JS engine
and Python reference. Added a Python twin of player-tags.js playerTag
to value_reference.py.

## Changes

- `pipelines/value_reference.py`: added `player_tag()` function (Python
  twin of player-tags.js), `_player_tags()` to populate rows, and four
  new fields in `rows()` output: lineup_share, start_worthy, ddf_tier,
  player_tag.
- `pipelines/value_check.py`: added `diff_categorical_rows()` for exact-
  match string fields; ENGINE_JS now extracts lineupShare, startWorthy,
  ddfTier and computes playerTag inline; `compare()` diffs these fields
  per view.
- `tests/test_player_tags.py`: added `PythonTwinTest` (2 tests) verifying
  the Python player_tag matches all JS fixtures plus the threshold
  override.

## Verified

- `value_check compare`: 905,952 values compared, 0 mismatches, verdict
  agree (all 12 combos: 3 scorings x 4 league sizes).
- `check_rank_guard.py`: 12 checks, 0 inversions.
- `test_player_tags.py`: 8/8 pass (6 JS + 2 Python twin).
- `test_expected_starts_model.py`: 39/39 pass (3 Live tests skip due to
  missing output/lineup-parameters.json in worktree).
- `test_derive_lineup_parameters.py`: 3/3 pass.

## Deltas explained

Zero deltas. The new fields were already computed identically by both
the JS engine and the Python reference; this change only adds the
comparison to value_check so future drift is caught.
