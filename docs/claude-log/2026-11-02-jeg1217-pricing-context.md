## 2026-11-02 - JEG-1217 / JEG-1255 pricing-context correction (PR #1084)

Contract: correct the P2 blocker from the independent delta review of `cf1301169b7d64caf94292be4a9b3823ea3e5d65`.
Manager draft appeal must use the pricing context that produced its opportunity rows. No value formulas, profile weights,
band thresholds, defaults, season labels or data horizons change.

`league.js` retains the completed search's `rowsByKey` values as `result.pricingRows`. `manager-recs-ui.js` passes that
snapshot into the existing recommendation builder instead of asking the engine for standard-bench rows. The same snapshot
covers scoring, team count, superflex, the league-roster toggle and custom settings, and remains consistent while a new
search is pending. No locked `app/v2/v2.js`, `app/v2/shell.html`, or `HANDOFF.md` edit is needed.

### Verified (check named)

- Before the fix, `RENDER_TESTS_REQUIRED=1 /Users/botcomp/code/fantasy-tools/.venv/bin/python -m unittest tests.test_jeg1217_managers_render.ManagerPricingContextTest`
  fails six subtests: Standard/Half PPR/PPR at 12 teams/1QB and 10 teams/superflex with league rosters enabled. Every
  positional draft curve differs from the independently requested league curve. The same test checks standard-bench
  fallback with the toggle off, draft-only and mixed-anchor profiles, full recommendation gains/order/bands/provenance,
  opportunity player prices and automatic DOM redraws. PPR's empty one-for-one results are accepted; its full curve is
  still checked, so empty output cannot hide the context bug. Sentinel inputs reuse the committed USO fixture without
  changing player identities or fixture data.
- `node --check app/v2/league.js`, `node --check app/v2/manager-recs-ui.js`, and `git diff --check`: pass.
- After the fix, `RENDER_TESTS_REQUIRED=1 /Users/botcomp/code/fantasy-tools/.venv/bin/python -m unittest tests.test_jeg1217_manager_profiles tests.test_jeg1217_manager_recs tests.test_jeg1217_managers_render tests.test_v2_league_levels_render.TestRenderedStates tests.test_jeg1389_switch_redraw_render tests.test_v2_contract_render`:
  18 tests passed, no skips, including the new pricing regression and the contract suite's broken-build guards (547.986s).
- Local full `make validate` skipped after live `pgrep -fl "make validate"` found another run (PID 97163). Its full-gate
  replacement is exact-head CI. Browser suites run sequentially on Playwright 1.63.0 / Chromium 1243.

### Claimed, not confirmed

- Independent high-risk delta review is a separate job and is still required on the pushed fix head. This author pass
  is not a review receipt. No merge, deployment, Supabase action or production change was performed.
- F1 is not applicable: this repository's pricing handoff does not exercise Cyrus's F1 workflows. Verification uses
  this repository's focused and browser suites.
