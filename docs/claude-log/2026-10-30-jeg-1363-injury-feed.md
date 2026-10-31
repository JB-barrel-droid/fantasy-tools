## 2026-10-30 - Daily, dated injury display feed (JEG-1363)

Contract: diagnose the October 9 injury cutoff, reconnect the existing source,
and port #1191's chip over path A without editing v2.js or shell.html. Draft
only; no deployment, database writes/migrations, settings or secret changes.

### Verified (check named)
- Earliest stopped scheduled run, 38375192524 on Oct 13: the same canonical
  identity gate rejected `derive_lineup_parameters.py`'s resolve import.
  Later failures moved to projection_capture; the API itself kept responding.
- `gh run list --workflow sleeper-identity-refresh.yml` and the failed-step
  log for run 40848414836: the pull succeeded but the identity gate failed
  `test_player_resolution_uses_canonical_players` on projection_capture's
  injected resolver, preventing the commit. The dated base stayed at Oct 9.
  JEG-1386 repaired that gate on main; run 41098267164 succeeded Oct 30,
  and main's base now says `2026-10-30T17:22:40+00:00`.
- Existing storage: `data/inputs/sleeper_identity_base.json` feeds the bake's
  `players.json` injury_status and its identity_base_pulled_at; the separate
  `public.player_status_history` daily history has continued running (repo
  summary: Oct 30 13:10 UTC, 944 rows). No database query/write was needed.
- Source kept: Sleeper `/v1/players/nfl`, the existing keyless source.
  [Official documentation](https://docs.sleeper.com/#players) describes API
  access; this change introduces no provider, credential or licensing change.
- `python3 pipelines/pull_player_status.py`: snapshot as of
  `2026-10-30T22:44:16+00:00`, 869 team-backed QB/RB/WR/TE/K players.
  Examples: Jalen Hurts (6904, PHI QB) IR; Christian McCaffrey (4034, SF RB)
  Questionable; Baker Mayfield (4892, TB QB) no injury status. Missing status
  is not a claim of health. `make sync` ships that exact observation date
  and id map in `dist/v2/player-status.js`, independently of a value bake.
- The existing daily 13:10 UTC / Sunday 16:30 UTC workflow now publishes the
  status even if the database history step fails. Its history saver reuses
  the raw pull. Branch/dry runs never request Pages. A successful main push
  explicitly requests the existing validated Pages build (bot pushes do not
  trigger push workflows). Publication pause guards remain in place.
- `tests.test_daily_player_status`: partial/undated pulls preserve previous
  output; status joins use existing ids plus matching team/position; missing
  ids, cleared status and free agents cannot reuse the baked injury; 30-hour
  expiry (4 hours on Sunday, America/Chicago), future-date rejection, dated
  labels, and no row/value mutation. The behavioral check fails against
  origin/main's Waivers code (`Out` instead of `Questionable`).
- `tests.test_daily_player_status`, `tests.test_waivers_status`,
  `tests.test_validate_shards`: 27 tests OK. Earlier related identity checks
  also passed (59 tests). `actionlint` on the changed workflow passes.
  The old builder-date assertion now rejects identity-bake metadata: the
  displayed status date must come from the daily snapshot. The old redundant
  injuryNote mutation was replaced with its fresh-note positive control,
  because injuryNote now goes through the guarded statusOf too.
- Local sync succeeds using Python 3.12 and installed Chrome. The initial
  `make validate` attempt stopped during sync because this virtualenv's
  Playwright browser download was absent; use `CHROMIUM_PATH` for this Mac.
- Step 2 commit: `86fa5e3c`. Step 3 ports only #1191's player-flags helper,
  chip CSS and tests over path A's existing hooks. Neither `app/v2/v2.js`
  nor `app/v2/shell.html` is edited. `players.json` remains byte-identical to
  the base (SHA-256 `296c4d9d87a6647fd413a3fbb5f85c810cbf031e0936a7f0bb0fefa41c85c7c9`);
  the display snapshot matches 770 existing rows by Sleeper id. Missing IDs
  remain unshown, never name-matched or inferred.
- After the chip port, `tests.test_player_flags`, `tests.test_daily_player_status`,
  `tests.test_waivers_status`, `tests.test_validate_shards`: 38 tests OK.
  Includes the actual daily-map tooltip and suppression of a cleared/missing
  ID's baked Out status. Thirty of the 770 matched statuses changed between
  the recovered 17:22 identity bake and the 22:44 live pull (DeVonta Smith:
  Questionable -> Out; Lamar Jackson: Questionable -> no status).
- `make validate` ran with `RENDER_TESTS_REQUIRED=1` and installed Chrome.
  The hold/source render matrix passed all 59 tests (706.860 seconds).
  Another local validation started after this one; this gate paused between
  suites until that process exited, then resumed. The gate caught a raw
  timestamp parser call in this PR. The puller now uses the repository's
  `parse_iso_timestamp`; `tests.test_timestamps` plus the four status/chip
  suites pass all 46 tests. Remaining exact test-core commands were resumed
  from after that corrected stage, rather than repeating the passed matrix.
- Resumed core stopped at the user-named known red:
  `FinderSavedTeamRenderTest.test_keyboard_mobile_and_overlap_guard`, line 415,
  selected team `''` rather than `beta` after Home/ArrowDown/Tab. The other
  ten tests in that module passed; no assertion or unrelated UI code changed.
- `make value-check-compare test-integration`: passed. Engine/reference
  comparison checked 1,234,651 values, zero mismatches (max difference zero).
- `/tmp/JEG-1363-browser-check.py` on built `dist/`: all 12 combos
  (standard/half PPR/full PPR x 8/10/12/14 teams) retain identical values with
  path A's helper versus the chip helper; `fixedPieIndexed` true everywhere,
  zero page errors. Compare renders IR and Q chips with the observed
  `Oct 30, 22:44 UTC` date in accessible tooltips. Desktop and 390 px mobile
  screenshots are in `output/playwright/`; mobile scroll width is 390 px.
  Replacing the observation with Oct 9 yields no chip on render and leaves
  every value unchanged. `JEG-1363-browser-check.json` records the comparison.
- `tests.test_waivers_math` and `tests.test_waivers_views`: four tests pass.
- `tests.test_v2_contract_render`: all six tests pass, including the live
  contract and the deliberately broken-build guard checks, with rendering
  required. The unrelated known USO journey red was not rerun.

### Claimed, not confirmed
- Scheduled publication and production UI behavior need this PR merged and
  the existing scheduler to run. Neither was triggered in this session.
- Independent Claude review remains required before merge; this session
  neither merges nor deploys.

## Review corrections — JEG-1401 / JEG-1402

### Verified
- Restored the shared six-day Waivers rule for the daily map, superseding
  this entry's earlier 30-hour/Sunday-four-hour policy. Regression cases show
  Sunday's 16:30 UTC copy at 21:05 UTC and a 5-day-23-hour copy; six days plus
  one minute is hidden. Future/undated copies and missing-status suppression
  remain covered.
- History setup and collection run unless cancelled; a missing shared file
  omits --from-file so the saver performs its own pull. A shell-stub test
  exercises both cache branches without database access. The no-rebase push
  has an explanatory comment preserving the repository's no-rebase rule.
- Requested unit modules (waivers_status, player_flags, daily_player_status,
  timestamps): 30 tests pass. Both updated regressions reject the prior head.
  actionlint passes for player-status-history.yml.
- tests.test_v2_contract_render: six tests pass with RENDER_TESTS_REQUIRED=1
  and installed Chrome. Locked v2.js/shell.html and value math are unchanged.

### Claimed, not confirmed
- Production scheduling/history writes remain untested; no Supabase writes,
  merge, deploy or credential changes were performed.
