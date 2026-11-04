## 2026-11-03 - versioned site boards / JEG-1419

Contract: continue draft PR #1264 on `be/JEG-1419`, merge current main normally,
and verify the 24-setting site board build, deterministic archives and previous
week retention. No engine, value math, weekly producer or Supabase changes.

### Verified (check named)

- GitHub PR inspection: #1239 merged as `89cc7a08`; #1264 was still draft at
  `3db469e4`, with no newer ownership claim. Jeremy approved the Linear claim.
- Merged pinned main `ad0cfc3a` into the existing branch as `1f23d30c` without
  rebase or force push. The docs index conflict retains both sides' entries.
- Archive inspection: all 24 committed week-8 boards pass
  `pipelines/lib/waiver_board.py` validation and their manifest SHA-256 values
  match. The original site board rerun test passed (1 test, 59.742s).

- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest
  tests.test_site_waiver_boards tests.test_build_weekly_inputs tests.test_build_waiver_board`:
  143 tests in 228.564s; 142 passed, one unchanged golden fixture failed.
  The expanded site test passed: exact 24 settings, manifest hashes, stable
  rerun bytes, and clean next-week recovery retaining prior boards and metadata.
- The golden failure is `Determinism.test_cli_output_matches_the_committed_board_byte_for_byte`.
  A recursive JSON comparison finds only `/inputs/weekly_inputs/sha256` differs:
  actual `2fcf34ed369cac27d9276308b0b2e22d279af0d56e89c11caa7a39500e4bff1b`,
  expected `b725cf300623a9fbe9b9b0c0779f710bf3fd42146400688521fd86bb6ca11655`.
  Builder, test and fixtures are byte-identical to pinned main `ad0cfc3a`.
  No fixture assertion or producer file was changed.

### Claimed, not confirmed

- Full `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make validate`
  completed sync and guard-harness, 26 reference tests, 29 engine tests,
  3 stability tests, 3 promotion tests and 36 static-export tests successfully.
  It has reported an error (`E`) in `tests.test_seeded_hold_build`'s browser
  matrix and is still finishing that suite. The traceback and final exit are
  pending, so this is not a green validation receipt. Its test and engine files
  are unchanged by this PR. Log: `/tmp/jeg-1419-validate.log`; execution session
  `75796`. Do not cancel or rerun it blindly.
- Review is blocked on a complete green gate and current-head CI. Draft PR
  checks defer expensive validation until the coordinator marks the PR ready.
- No independent review, merge, deployment or live verification performed.
- Automatic approval review denied changing Linear status and dependency fields;
  those fields remain unchanged. The ownership claim itself succeeded.
