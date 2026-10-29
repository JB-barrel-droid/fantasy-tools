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

## Aligned to the JEG-1227 contract (second push)
- Output now follows `weekly-inputs` 1.0.0 from branch
  `claude/JEG-1227-weekly-inputs-contract` (`e2a2a07`): `players`, `built_at`,
  `schema_version`, per-leg `kind`/`content_season`/`captured_at`, cell
  `values` + per-key `missing_reason`, scoring keys `standard/half_ppr/ppr`,
  bye values `{bye_week}` only.
- Leg `content_week` is the content week of the newest capture, so the
  contract's freshness rule (artifact week minus leg week) holds.
- `--players` is now required (the contract needs a name and position per row);
  an unresolved ESPN row with no name in its source is named after its source id.
- Only the season `nfl_week.py` defines (2026) is accepted.
- Status fields Sleeper leaves unset (a healthy player's injury fields) are
  null with "not set in the Sleeper record", provenance partial, as in the
  contract's own fixtures.
- Read-only check of `public.player_status_history` (2026-10-29): minimum
  `depth_chart_order` is 1, latest day 2026-10-28 with 951 rows, so stored
  rows fit the contract's status units.

## Verified (second push)
- With the JEG-1227 module copied in locally (not committed):
  `python3 pipelines/lib/weekly_inputs_contract.py tests/fixtures/weekly_inputs_producer/expected_wk8.json`
  OK, 0 errors, 0 warnings; the real week-8 run (478 players) also validates;
  `python3 -m unittest tests.test_build_weekly_inputs` 35 OK.
- Without it (this branch as pushed): 35 run, 1 skipped (the contract test).
