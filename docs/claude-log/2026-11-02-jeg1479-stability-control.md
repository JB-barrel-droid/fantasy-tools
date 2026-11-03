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
