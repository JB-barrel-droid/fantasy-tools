## 2026-11-02 - JEG-1323 review corrections (PR #1174)

Contract: fix the independent review's two blockers on `claude/JEG-1323`, plus
the reported 2QB context label; return a pushed, CI-verified head for independent
delta review. Jeremy authorized this fixer job and the normal branch push.

### Verified (check named)

- `node --test tests/node/jeg1323_review_regressions.cjs` against reviewed head
  d2e11c68: all nine named tests fail before the fix (three defects × three
  scorings). Opposing selected/default values reproduce a displayed 30 versus
  market 20 with gap -10. K/DEF throw-ins erase priced acceptance charts.
- The adapter now maps the selected basis into `marketGaps`' existing input key
  without mutating engine rows; the same existing gap and noise-floor helpers
  supply the displayed gap and direction. Acceptance excludes K/DEF from the
  `evaluateCombo` inputs while preserving the physical trade and roster counts.
  Context derives the QB count from known shape and leaves unknown superflex
  settings unknown. No valuation formula, source data, or weekly/ROS rule changes.
- `RENDER_TESTS_REQUIRED=1 .venv/bin/python -m unittest -v
  tests.test_jeg1323_trade_readout_rows tests.test_jeg1230_trade_readout`: four
  tests pass, including all nine new cases and the unchanged golden.
- Sequential required browser suites: `tests.test_jeg1323_trade_readout_render`
  passes (one test, six desktop/phone scoring cases); then
  `tests.test_jeg1230_trade_readout_render` passes (two tests). No skips.
- `.venv/bin/python -m unittest -v tests.test_v2_finder_fit
  tests.test_v2_finder_trifit tests.test_jeg1213_logic
  tests.test_jeg1229_trade_context tests.test_render_sweep_shards`: 15 pass,
  one fails on both the PR checkout and fresh `origin/main` 3799ff1e. Only
  `test_trade_context_contract` fails: JEG-1240 journey calls `envelope` with a
  mismatched signature (`uso_site_journey_contract.cjs:136`, undefined
  `state.settings`). Journey/context files are identical to main. The other
  four modules are green, including the render-list shard guard.
- `git cat-file -e origin/main:pipelines/baseline_reds.py`: no such file;
  it is absent on the PR too. The journey failure is main-red, not attributed
  to an allowlist or this PR. No unrelated assertion was weakened to hide it.
- Live `pgrep -fl 'make validate'` found another validator (PID 62269).
  Per Jeremy's instructions, local full validate was not started; focused and
  required render checks continued. No other job was stopped or cancelled.
- `git diff --check` passes. No edits to `app/v2/v2.js`, `app/v2/shell.html`
  or `HANDOFF.md`; no main catch-up was needed for these adapter corrections.
  Generated render-build churn is excluded from the correction commit.

### Claimed, not confirmed

- Exact-head CI is checked after the single push; the ticket and bridge receipt
  hold that result and the resulting head SHA. This log does not claim CI before
  it runs.
- Independent delta review remains required. This is the author's correction
  report, not a review or approval. No merge, deploy or live-output claim.
