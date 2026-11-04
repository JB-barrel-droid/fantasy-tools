## 2026-11-03 - validation repairs / JEG-1419

Contract: investigate the existing golden mismatch and held-source browser error
on `be/JEG-1419`, using the original active validation run. Leave the denied PR
body and Linear field updates untouched; preserve existing ownership.

### Verified (check named)

- `git show 1df5f4c2 -- tests/fixtures/weekly_inputs_producer/expected_wk8.json`
  shows the weekly golden's alias-file provenance hash changed. The downstream
  board golden was not updated. Comparing a fresh CLI board against its golden
  finds exactly one differing field: `/inputs/weekly_inputs/sha256`.
- Corrected that one board fixture hash to the SHA-256 of the actual committed
  weekly-input bytes, `2fcf34ed369cac27d9276308b0b2e22d279af0d56e89c11caa7a39500e4bff1b`.
  No player, value, availability or test assertion was changed.
- Before: the original 143-test targeted run failed the byte-for-byte golden
  assertion. After: `python3 -m unittest tests.test_build_waiver_board.Determinism
  tests.test_build_waiver_board.HandWorkedRows tests.test_build_waiver_board.ValidatorCatches`
  passed all 54 tests in 0.309s. Log: `/tmp/jeg-1419-golden-repair.log`.
- Editing `tests/fixtures/**` requires high-risk independent review under
  AGENTS.md. The coordinator must account for this floor; no review labels,
  Linear fields or PR body have been changed in this follow-up.

- The original full validation completed without cancellation, exit 2:
  `tests.test_seeded_hold_build` ran 59 tests in 1993.265s, with 58 passing
  and one error in `SourceScenarioRenderTest.test_cbs_held_lagging`.
  The third browser session timed out at `page.wait_for_function(W.READY)`
  after the unchanged 30-second deadline (`tests/test_seeded_hold_build.py:308`).
  Original log: `/tmp/jeg-1419-validate.log`.
- After that process exited, the exact failing case was rerun once with
  `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest -v
  tests.test_seeded_hold_build.SourceScenarioRenderTest.test_cbs_held_lagging`.
  It passed unchanged in 176.230s, including all three browser sessions and
  all source/lagging/rank assertions. Log: `/tmp/jeg-1419-held-browser.log`.
  No timeout, assertion, browser test or engine implementation was changed.

### Claimed, not confirmed

- The cause of the original readiness timeout remains unproven. A passing
  isolated rerun is not a green full-validation receipt or proof of a fix.
- Required remaining gates on the corrected head:
  `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make validate`,
  the contract check `python3 -m unittest tests.test_v2_contract_render`,
  current-head full preview/render CI, and independent high-risk review.
  The original gate stopped at Makefile:672 before `test_isolate_post_validate`
  and the rest of test-core, `value-check-compare`, and `test-integration`.
- The PR remains draft. Its expensive preview/render jobs are deferred by
  draft state, and the finalizers are red; settings-render, security contracts,
  waiver mutation and PR-state passed on prior head `efa7947a`.
- The denied PR body and Linear field updates remain untouched.
