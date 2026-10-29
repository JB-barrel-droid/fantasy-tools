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

## JEG-1245 corrections (third push, Codex review 2026-10-29 03:25)
- Fails closed: `_basic_check` is gone. `_load_contract()` imports JEG-1227's
  `weekly_inputs_contract` before any input is read; a missing module, one that
  raises on import, one without `validate`/`errors`, or a validator that
  crashes refuses the run (exit 3) and writes nothing. Old head returned `[]`
  for a golden with `schema_version` 999.0.0 and no contract.
- Offline identity: `canonical_players.Registry` reads aliases through
  `player_aliases.load()`, which asks Supabase whenever `SUPABASE_URL` and a
  key are set and only logs a failed request. The producer now pins that load
  to a local file (`--aliases`, default `data/inputs/player_aliases.json`)
  while the registry is built and restores it after. No shared lib edited.
- Provenance: `input_report.identity` records the alias file name and sha256
  with `alias_source: local_file`. That block is the only golden change.
- Tests: until JEG-1227 is on this branch, producer-logic tests use a
  test-only stub validator; the subprocess CLI test asserts the real refusal.
  New classes `ContractFailsClosed` and `OfflineIdentity` (network spy on
  `urlopen`, `create_connection`, `socket.connect`/`connect_ex`, records
  without raising; a control test proves it sees the old Registry attempt).

## Verified (third push)
- `python3 -m unittest tests.test_build_weekly_inputs`: 47 OK, 2 skipped
  (both need JEG-1227 on the path). With S1 `e2a2a07` copied in locally (not
  committed): 47 OK, 0 skipped; same with dummy Supabase credentials set.
- S1 `validate` on the regenerated 11-player golden: 0 errors, 0 warnings;
  999.0.0 gives `version.unsupported_major`.
- Probe at 2da0242 vs this head, contract missing, dummy credentials:
  validate(999.0.0) `[]` -> ContractUnavailable; network attempts during
  Identity 1 (`.../rest/v1/player_name_aliases`) -> 0.
- Real week-8 run (478 players) with dummy credentials: S1 0 errors,
  byte-identical on repeat, no Supabase log line.

## JEG-1267 alignment (fifth push, S1 #1087 at 86c854d)
- The corrected S1 validator rejects an aged or `published` leg with a null
  content_season, content_week, content_vintage or captured_at
  (`leg.provenance_unknown`). The bye table stamps none, so the bye leg is now
  freshness `unknown`, label `modeled`, `content_week` null, with a `note`
  (option b on JEG-1245; the contract's own `valid/unknown_no_provenance.json`
  shape). No date is invented.
- Same rule for any leg whose input lacks a vintage or a capture time (a
  status export without `fetched_at`): unknown/modeled, content_week null, the
  stamps it does carry kept.
- Golden diff: the bye leg meta only.
- Verified: 50 OK against 86c854d (with and without dummy Supabase creds);
  50 OK, 1 skipped against e2a2a07; 50 OK, 3 skipped with no S1. Golden and
  the real 478-player week-8 run: 0 issues against 86c854d, real run
  byte-identical on repeat.
