## 2026-11-03 - Greedy package selection / JEG-1183

Contract: implement the settled greedy, re-checked selector as an isolated companion to the selected-package preview.
Reuse the existing finder assessment, viability and ranking rules, and the merged package roster helper. Shared
finder/opportunities/league/v2 files stay with their integration owners. T2 build; parent review-high-risk applies.

### Verified (check named)

- Linear JEG-1183 and latest comment read; `gh pr list` and a targeted GitHub PR search found no matching open PR.
  The latest old WIP hold is superseded for this bounded implementation by the explicit delegated work request.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest
  tests.test_package_composition_preview_contract tests.test_package_composition_preview_render
  tests.test_jeg1183_package_constraints`: 15 tests pass. Ten selector scenarios, a missing-selector negative
  control and four mutation controls exercise greedy rechecks, ranking and roster invariants. The real browser
  selector/helper/starter-picker case proves three counterparties, uniqueness, changed final starters and sequential
  roster equality at 390/1280 px. The pre-existing preview scenarios and mutation guards still pass.
- `node --check app/v2/trade-package-search.js` and `git diff --check` pass.
- Final combined selector, preview, roster helper and built-page contract run passes all 21 tests in 558 seconds
  with `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1`. This includes the ten selector scenarios and
  all existing built-page contract mutation guards; no rendering skips.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make value-check-compare test-integration` exits 0.
  The strict engine/reference comparison and all integration modules pass separately after the baseline failure.
  The final Node package-contract suite was rerun after aligning synthetic entry positions with engine-row positions:
  all 7 tests pass. Browser fixture defaults and production code are unchanged by that test-only adjustment.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make validate` built successfully, passed the guard
  harness and 55 engine/reference tests, then stopped at the existing fractional-seat negative control:
  `test_hard_rule_fails_the_bound` measured 0.0 and expected more than 1.0. Its positive stability check passed.
  Running that single negative control in a pristine detached worktree at base
  `a552c00884287147a099a1279c94b3fdb0d4ca88` reproduces the exact same failure (no selector changes present).
  The remaining test-core commands did not run after that failure. This is the recovery lane's existing blocker,
  not a passing full validation gate; no test or valuation-engine change was made to bypass it.
- Automatic approval review rejected the attempted Linear child creation and In Progress mutation: it considered
  ticket-state changes outside the delegation's implementation/draft-PR authorization. No child or claim executed;
  no retry or alternate ticket mutation was attempted. Existing-ticket ownership metadata remains unchanged.
- Linear `get_agent_context` returned tool-not-found; no shared notes were obtained from it.

### Claimed, not confirmed

- Exact-head CI and draft-PR publication follow this implementation commit. Heavy remote checks are deliberately
  deferred for a draft PR; no full-green CI, review receipt or release readiness is claimed.
- Production route/panel integration, independent high-risk Claude review, merge, deploy and live-site verification
  remain later gates. No production values or pricing formulas change in this isolated selector.
