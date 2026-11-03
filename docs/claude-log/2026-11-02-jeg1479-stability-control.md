## 2026-11-02 - Deterministic stability control / part of JEG-1479

Contract: prepare a local test-only repair for the failed data-publication
negative control. Preserve the live-input positive scan, its 1.0 DDF Value
bound and 1.0 PPG perturbation; no push, merge, deploy or production changes.

### Verified (check named)

- Repository API identifies `datadrivenfootball/fantasy-tools` as repository
  1380582050. Branch `codex/JEG-1479-deterministic-stability` starts at
  `79288f1a0239f98af5e221750f4897aef12e55cb`.
- That head's `dist/modules/comparison-chain-status.json` records run
  `2026-11-02T20:12:57.506915+00:00`, seven successful source reviews, no
  holds, and a failure recorded at `20:18:51.982336+00:00` in
  `test_hard_rule_fails_the_bound`: 0.19351198825178084 is not greater than
  1.0. This is the control's invalid assumption about current inputs, not
  evidence of a failed positive stability bound.
- The old test passes on the committed, last-published inputs: `worst_move`
  returns 3.8502566426283096. Failed candidate inputs were not published;
  do not confuse this local result with the failed rebuild's inputs.
- `/tmp/jeg1479-evidence/reproduce-old.py` executes the original test from
  `git show 79288f1a:tests/test_fractional_seats_stability.py` against stable
  synthetic `VR.Inputs`: old control fails at 0.05577985889417647; corrected
  controls pass with the same cached inputs. This independently reproduces
  the bad premise, not the exact unpublished candidate.
- `test_hard_rule_fails_the_bound` now uses fixed synthetic projections and
  one fixed chart on the Charlotte shape. RB31's ESPN projection alone falls
  1 PPG: its three-source mean crosses WR28, RB flex seats go 7 to 6, WR flex
  seats go 3 to 4. All 319 other players are priced. Their largest hard-rule
  move is 2.9820405932163716 (synthetic key 237).
- `test_fractional_rule_smooths_known_crossing` checks the identical inputs
  at production sigma 0.75: largest other-player move 0.3946559192143386.
  Both controls pass with `VR.Inputs.load` patched to raise. Forcing sigma
  back to 0 makes the new fractional test fail at 2.9820405932163716 > 1.0.
- An AST comparison confirms `test_no_other_player_moves_more_than_one`
  is unchanged. Its standalone live-input run passes across all 14 settings.
- Focused command: `python3 -m unittest tests.test_fractional_seats_stability
  tests.test_fractional_seats tests.test_fractional_seats_engine
  tests.test_fractional_seats_worked_example tests.test_fractional_seats_pie`:
  26 tests, 25 pass, one unrelated failure in untouched
  `ContinuityTest.test_crossings_are_continuous` (no bench crossing within
  1.5 PPG). Running that test alone reproduces it without loading the changed
  stability module. No change to that separate control is included.
- Evidence logs and reproduction script are in `/tmp/jeg1479-evidence/`.
  Full validation runs in a separate detached worktree so generated build
  outputs do not enter the repair patch.
- `env -u SUPABASE_URL -u SUPABASE_SERVICE_KEY
  CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make validate` has
  passed the build, engine/reference checks, all three stability tests
  (48.099 seconds), all 59 seeded-hold tests, rank/superflex checks and the
  subsequent suites through hamburger navigation. It remains running in
  desktop-menu rendering at the parent's immediate checkpoint request.
  Execution session: 66684; worktree:
  `/workspace/fantasy-tools-stability-validation`; log:
  `/tmp/jeg1479-evidence/validate.log`. No full-gate success is claimed.

### Claimed, not confirmed

- No remote push, independent review, release or live recovery has occurred.
  Parent coordinator owns these steps. CBS own-snapshot discrepancies and
  Razzball publication lag remain separate.
- Full validation is pending as described above. Parent reports PR #1255 has
  a separate shard-5 failure; this repair includes no attempt to fix it.
- Raw GitHub Actions log download was denied by network policy at
  `results-receiver.actions.githubusercontent.com`. The committed failure
  receipt above was verified; the exact unpublished failed inputs were not
  obtained or replayed.
- Linear's advertised `get_agent_context` tool returned tool-not-found.
  Automatic approval review rejected creating an implementation ticket:
  external organizational commitment lacked exact trusted user authority.
  No ticket creation or ownership mutation occurred; parent must handle it.

---

## 2026-11-02 - Main #1247 integration checkpoint

Contract: integrate actual main after #1247's functional test changes, preserving
the previously reviewed feature and shared canonical fix. Prepare the next head
while the coordinator verifies main's deployment; no PR merge or deployment here.

### Verified (check named)

- Fetched actual main at `1df5f4c20032a794918637f72cb796673b95e93d` and
  merged it normally into the existing branch as `5f331cff9d421afbafb9b243f737b9856ffe5321`.
  Git reported no conflicts. Existing work and all incoming logs were retained.
- `git diff --exit-code fce8f521 HEAD -- tests/test_fractional_seats_stability.py
  tests/test_launch_front_door.py` passed: both feature tests and the shared
  canonical correction are byte-identical to the preceding green head.
- Destination-identity, required-runtime focused checks passed: 128 tests in
  1.847 seconds, no skips. Modules: `test_build_weekly_inputs`,
  `test_weekly_inputs_contract`, `test_week_state`, `test_week_stale_deadline`,
  `test_no_real_clock`, `test_org_cutover`, plus both fixed fractional crossing
  controls. These exercise producer determinism, weekly/DST boundaries,
  repository cutover and the preserved hard/fractional control pair.
- No broad local validation was repeated. No separate continuity repair,
  production math change, force push, deletion or manual CI cancellation.

### Claimed, not confirmed

- The integrated final head requires fresh CI; preceding-head green checks
  are inherited evidence only. Later operational-status-only main drift is
  covered only by Jeremy's current-batch option A, not functional changes.
- The coordinator owns deployment recovery, the final-main comparison,
  independent current-head receipt, merge and serial live verification.

---

## 2026-11-03 - Main #1255 integration checkpoint

Contract: integrate current functional main once after #1255; preserve the
reviewed stability repair and prepare fresh CI on the existing ticket branch.
The coordinator retains serial merge and release ownership.

### Verified (check named)

- Fetched actual main `832a18d90704ffa547ad5aae22e179e28843f3f1`, containing
  #1255 merge `4c60f8fd0e631f3fb961174f9be8f9f77ab67796`, and merged normally
  as `55eac0e3efc2ea706c235acfa95e0201bee6cdc5`. No conflicts; all incoming
  work retained, including baseline attribution and dispatched-code hash.
- `git diff --exit-code 1bfc656e HEAD -- tests/test_fractional_seats_stability.py`
  passed: the reviewed feature test file remains byte-identical.
- Ran `python3 -m pipelines.baseline_reds --context local -- python3 -m
  unittest tests.test_baseline_reds tests.test_draft_ci_workflows
  tests.test_preview_workflow_matches_pages tests.test_ci_speedup_workflows
  tests.test_fractional_seats_stability` with destination repository identity,
  Chromium and required rendering configured, production write credentials
  unset. All 81 tests passed in 48.305 seconds, exit 0, no skips. This includes
  the unchanged live-input positive gate and both synthetic controls under
  the newly integrated wrapper, plus failure-preserving attribution checks.
- No duplicate broad local suite, production math change, continuity repair,
  force push, deletion, manual job cancellation, deployment or merge to main.

### Claimed, not confirmed

- Fresh final-head CI remains required; earlier green heads do not substitute.
- Later status-only drift uses the existing batch exception. Functional drift,
  independent current-head review and serial release remain the coordinator's
  responsibility.

---

## 2026-11-03 - Authorized main-repair bootstrap preparation

Contract: prepare #1287 first to repair the existing main negative-control
failure. The coordinator relayed Jeremy's specific "Y" authorizing that one
bootstrap merge despite existing main red, with recovery verification before
any other release. PR CI and independent review remain required; this session
does not merge or deploy.

### Verified (check named)

- Fetched actual main `75d43a5f893a47f4a8806149dd551bcaf22031fd` once and
  merged normally as `25bef22a1db85160b90fe2656c540150967d1c61`, no conflicts.
  Preserved #1277's journey/workflow changes, Sleeper identity refresh,
  weekly inputs, generated traces and operational status updates.
- `git diff --exit-code 1ab7cadf HEAD -- tests/test_fractional_seats_stability.py`
  passed. The reviewed deterministic repair is byte-identical; file SHA256
  `21e31ec94eb220c019d4ec82f2149f369e375bfd757b968615c03b058ac4b0e4`.
- Current main's committed comparison-chain status still identifies the old
  negative control failing at `0.6097403935206955 not greater than 1.0`.
  This is status-artifact evidence, not a replay of unpublished candidate data.
- Focused local checks through `pipelines.baseline_reds --context local`
  passed all 121 tests in 181.429 seconds, exit 0, no skips. Modules:
  `test_fractional_seats_stability` (full unchanged live sweep and both controls),
  `test_sleeper_identity_layer`, `test_espn_weekly_store`, `test_v2_finder`,
  `test_v2_finder_search_unchanged`, `test_baseline_reds`,
  `test_draft_ci_workflows`, `test_preview_workflow_matches_pages`,
  `test_ci_speedup_workflows`, `test_render_sweep_coverage`.
  Production write credentials were unset; destination identity and required
  Chromium configured. No tracked test-generated changes remained.
- No threshold, production math or separate continuity change. No duplicate
  broad local suite, force push, deletion, cancellation, merge or deployment.

### Claimed, not confirmed

- Fresh final-head CI and the coordinator's current-head review remain
  necessary. The main-red exception does not waive either gate.
- The live site has not been checked here. The coordinator owns serial merge,
  main/deployment recovery and live verification before any other release.

---

## 2026-11-03 - Reuse reviewed journey readiness correction

Contract: parent matched #1287's journey failure to the independently reviewed
boot-readiness correction in #1174 at `427c34053bf4dc393435f5056fa3b28b0b3c8a9a`.
Reuse exactly that correction; no new fix, timeout increase or assertion waiver.

### Verified (check named)

- On head `5bc447ac`, render run `41639625863`, journey job `125929600826`,
  failed the unequal subcase of `LeagueSiteTest.test_league_to_compare_journey`:
  no Details button for `164,2807|3942,1483` (24 tests, one failure).
- Compared the actual file to the reviewed head: the only differences are
  `settle()` requiring `ui.ready` before idle and a late-boot test reusing the
  complete existing journey. The source commit is
  `7e3abb6b65e3396579ceffe1111a421565f68187`; its test is unchanged at the
  reviewed head. It applied cleanly as normal cherry-pick `9f575740`, with
  original provenance and `2026-11-03-jeg1323-journey-readiness.md` retained.
- `git diff --exit-code 427c3405 -- tests/test_jeg1249_league_site_render.py`
  passed. The adopted test file is byte-identical to the reviewed correction,
  SHA256 `9dbff9b8a88ac1e75aa87908b260cab1ebd28efdbb4d31186c830384a25d1bda`.
- In a separate validation worktree on the integrated source plus that exact
  file, required-browser focused checks passed 4/4, no skips, in 162.849s:
  ordinary and delayed-boot league-to-Compare journeys, plus both deterministic
  stability controls. Both journeys retained equal/unequal IDs, exact values,
  workspace assertions, league-roster holds and original timeouts. Destination
  identity and Chromium configured, production write credentials unset.
- `git diff --exit-code 5bc447ac HEAD -- tests/test_fractional_seats_stability.py`
  passed. The reviewed stability fix, live gate and 1.0 bound remain unchanged.
  `git diff --check` passed. No application code or fixture change was added.

### Claimed, not confirmed

- Fresh final-head CI and parent-owned integration review remain required.
  No workflow was manually cancelled or retried. No broad local suite repeated.
- Parent retains the authorized bootstrap merge and recovery verification;
  this session performs no merge to main or deployment.

---

## 2026-11-03 - Player-status input integration

Contract: parent found functional player-status input drift before bootstrap.
Integrate current main once, preserve both qualified test fixes, run focused
checks and fresh CI. Do not chase later operational status-only commits.

### Verified (check named)

- Fetched actual main `a552c00884287147a099a1279c94b3fdb0d4ca88` once.
  Incoming changes comprise `data/inputs/player_status.json`,
  `output/player-status-history.json` and seven operational JSON files.
  Merged normally as `8ef0bbd3f7e4c745a61000ef2ffbced7c70e97a9`, no conflicts.
- The status snapshot is now dated 2026-11-03T13:10:15+00:00 and the history
  summary records 948 rows. All incoming data and operational artifacts retained.
- `git diff --exit-code cc25702a HEAD -- tests/test_fractional_seats_stability.py
  tests/test_jeg1249_league_site_render.py` passed: both qualified fixes are
  byte-identical to the preceding green head.
- Through `pipelines.baseline_reds --context local`, all 9 tests in
  `test_daily_player_status` and `test_fractional_seats_stability` passed in
  165.028s, no skips, exit 0. Includes the unchanged live sweep and 1.0 bound,
  both deterministic controls, status expiry/value invariance and daily publish
  behavior. Production write credentials unset; required Chromium configured.
- All 3 plain test functions in `test_player_status_history_ids` passed using
  `unittest.FunctionTestCase` adapters (0.121s, exit 0). Pytest is unavailable in
  this runtime; the existing no-argument functions and assertions ran unchanged.
- No tracked generated churn. No broad local or browser suite repeated. No
  application source, math, bound, assertion or timeout change added.

### Claimed, not confirmed

- The integrated head requires new exact-head CI and parent qualification of
  this delta. Previous-head green checks do not replace those requirements.
- Parent retains the specifically authorized bootstrap, main/live recovery
  verification and serial release; no merge, deploy or cancellation here.
