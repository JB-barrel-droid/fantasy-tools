# JEG-1228 offline weekly-input producer (Claude, 2026-10-29 UTC)

Slice S2 of JEG-1195. Branch `claude/JEG-1228-weekly-input-producer`, draft PR for Codex review.

## What changed
- New `pipelines/build_weekly_inputs.py`: explicit local inputs (ESPN weekly CSV,
  `player_status_history` JSON export, bye table, optional players snapshot and
  Sleeper identity base) to an explicit `--out` path, schema `weekly-inputs-v1`.
  No network, Supabase, schedule or wall clock (`--as-of` is the clock).
- New `tests/test_build_weekly_inputs.py` (33 tests) and
  `tests/fixtures/weekly_inputs_producer/` (invented players and teams, golden
  `expected_wk8.json`). One `test-unit-modules` line in the Makefile.

## Choices (logged in the picks log)
- ESPN leg vintage is the newest `snapshot_at` for the target week, because
  `save_espn_weekly.py` writes a row only when a number changes.
- Status uses the newest `snapshot_date` on or before `--as-of` and inside a
  content week no later than the target; older days are counted, not carried forward.
- Conflicting duplicates (same newest snapshot, different values; two Sleeper
  ids on one key) give `null` plus a reason, never a pick between them.
- A ROS column (`ros*`, `r_*`, `weeks_covered`, `season_block*`) or a non-`week`
  horizon refuses the whole run and writes nothing.
- `experts.ecr_weekly` and `vegas` are always unavailable here (no producers).

## Verified
- `python3 -m unittest tests.test_build_weekly_inputs` 33 OK.
- `python3 -m unittest tests.test_timestamps tests.test_pipelines_import_standalone tests.test_run_suite tests.test_doc_staleness` OK.
- Real stored-input run (ESPN weekly CSV + byes, week 8, as of 2026-10-29T02:00Z):
  478 rows, two runs byte-identical; status unavailable (no stored export in git).

## Claimed, not verified
- Validation against the S1 contract: JEG-1227 had not pushed when this was
  written; `validate()` uses `weekly_inputs_contract.validate` when it is on the
  path and a minimal structural check until then.
