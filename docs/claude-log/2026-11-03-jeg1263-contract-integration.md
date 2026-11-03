## 2026-11-03 - Simplified site completed-contract wiring (JEG-1263)

Contract: wire the completed context, readout and lineup prerequisites in the existing dashboard's Simplified site section,
without fabricating recommendations before the separate #1084 provider is available. No value or recommendation math,
second saved store, shared bootstrap/finder/shell changes, Fieldnotes changes, merge or release.

### Verified (check named)

- Ownership: fresh JEG-1263 comments ended November 2; #1217/#1233/#1283 are merged. A fresh open-PR file scan found
  no Simplified module/test writer. Existing remote Simplified/restoration branch commits date October 29. Operations
  identifies this existing session `01a19e2c-1d9b-712e-a55e-eecbd8b04020` and preserves separate #1084 owner
  `01a19e10-8dab-779d-b48d-70d1e8bec017`. Explicit bounded claim posted on JEG-1263 (marker
  `codex:jeg1263-contract-integration-20261103-claim`); provider label changed to codex on Jeremy's current direction.
- Branch `codex/JEG-1263-contract-integration`, base `040474c552a324921bdc7f71008ab6da3f823629`. Authored paths are
  `app/v2/simplified-site.js`, its existing unit harness/unit module/render module, and this log. No .agents skills were
  present. Linear get_agent_context returned Tool not found; repository contracts were read directly.
- Adapter now builds immutable `TradeValueTradeContext.fromLeague` context from active league settings, basis, overrides,
  sources and the starred saved team. Readout/lineup readiness comes from the actual shared APIs, not never-set rollout
  flags. Missing runtime contracts still withhold the answer. Only the ideas provider remains missing on current main.
- `readoutFor` delegates to shared `TradeValueReadout.inputFromContext/build` and the existing reserve rule. It consumes
  the completed search's `pricingRows` (#1084 contract), never standard-bench `getAllRows()` as a substitute. Missing
  moving players/unpriced values withhold the selected answer. Pending searches, a changed snapshot, null/Promise output
  remain loading. Existing league/profile/rows/search DOM events refresh the section; there is no polling or store write.
- `python3 -m unittest tests.test_jeg1263_simplified_site`: 3 tests pass, including all 20 logic checks and 19 mutation
  guards. New prerequisite, stale-search and snapshot/missing-player checks fail against the original adapter on base
  040474c5. Existing format, ranking, ROS-only, provenance and unavailable-input checks remain intact.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_jeg1263_simplified_site
  tests.test_jeg1263_simplified_site_render`: 10 tests pass (46.645s), no skips. Preserves seven-state synthetic harness,
  deep-link/Back/focus, fixture labeling and 1280/390/320 layout coverage. The new built-dashboard historical USO test
  verifies normalized Half PPR/starred identity, all three contracts ready and only ideas unavailable, league pricing
  on/off, unchanged serialized workspace, actual standard-bench trade readout and missing-player withholding. No mock
  recommendation provider is injected into the built dashboard.
- After adding source-store subscription coverage, the single loaded-dashboard test passes again (36.061s): clearing
  the star in the source workspace automatically updates the visible section to empty, without changing that source
  snapshot. Initial browser attempt exposed a nested Playwright test-harness error; fixed by reusing the class browser.
- `node --check app/v2/simplified-site.js` and scoped `git diff --check` pass. Build helpers regenerated app/trade-value-chart,
  history and dist output in this isolated worktree; all generated changes remain unstaged and excluded from the PR.

### Claimed, not confirmed

- Complete recommendation parity/acceptance awaits the real provider from #1084 (last observed open at
  `714bb4a5b20198effaff6cfc91c0102b8587606d`). This prerequisite slice is not completed product and is not a live-answer
  success claim. Do not duplicate its existing writer or alter ranking/fit/value formulas.
- No full make validate or broad suites were rerun: parent authorized focused prerequisite verification and prohibited
  duplicate broad tests. Draft CI is not a substitute for full required CI and an independent current-head review before
  release. Existing test assertions about rollout globals were replaced because those prerequisites have merged; actual
  runtime absence still fails closed, and flags cannot bypass it. No value, threshold or fixture assertion was weakened.
- No live-site request was retried: enforced network policy still excludes datadrivenfootball.github.io after the
  previous CONNECT HTTP 403 denial. No access change, Supabase operation, branch deletion, main push, force push,
  merge or deployment. Parent owns review risk classification, release and the remaining live journey.
