## 2026-11-03 - JEG-1217 / JEG-1255 integration after PR #1277

Contract: reconcile the real merge conflict against functional main after PR #1277, retain manager recommendations and main's context-preserving trade journeys, run focused integration checks, push the existing branch and follow exact-head CI. Parent retains independent review, merge and release ownership.

### Verified (check named)

- Main pin `22c88ea07adc6200f5d57dcfb8b41c2db995bec5` includes functional merge `698368f3` (JEG-1403 / PR #1277). Previous head `2d31f6e7e02acedf7812caeb5b0db3a097cda5aa` completed every PR CI workflow successfully.
- Normal `git merge --no-commit --no-ff 22c88ea0` has one textual conflict, `.github/workflows/v2-render-test.yml`. Keep main's contract/league/journey matrix and every main test command; schedule the existing manager profile/recs/render command exactly once in the league lane. Relative to main, the workflow adds only that three-line registration.
- No manual application edits. Main's `finder.js`, `overrides.js`, `v2.js` and league journey changes merge automatically. Relative to main, `league.js` retains the existing three-line result.pricingRows snapshot addition, so manager appeal still uses the completed search's exact prices. Canonical fix and manager modules are unchanged.
- Initial focused run through the baseline wrapper executes 65 tests: 64 pass; the exact render-command inventory guard fails because main's new inventory does not yet include this PR's existing manager command. The wrapper correctly labels it a new red and retains exit 1.
- Assertion expectation changed: add the authorized existing manager command to RENDER_COMMANDS in `tests/test_ci_speedup_workflows.py`. All equality, lane, missing/duplicate, fail-fast and failure-visibility assertions remain. Add a mutation that removes the manager command and must be caught. This strengthens the inventory; no coverage assertion or failure gate is weakened. Rerun only that affected module: all 14 tests pass, including mutation proofs.
- Six focused browser tests pass, no skips (78.660s): all three manager-card/pricing-context tests plus default-equivalent blend Compare context, oversized override hold, and the equal/unequal league-to-Compare journey. The latter exercises both standard-bench and league-roster paths. Required-render mode, `/usr/bin/chromium`, configured destination repository, normal make sync before loading browser tests. Across these runs, 71 distinct focused cases pass. Logs: `/tmp/pr1084-post1277-focused.log`, `/tmp/pr1084-post1277-workflow-fix.log`, `/tmp/pr1084-post1277-render.log`.
- `git diff --cached --check` passes. Generated build outputs stay unstaged and preserved. No duplicate broad validation suite was started.

### Claimed, not confirmed

- Fresh exact-head CI and independent high-risk delta review are still required. Historical green CI on the prior head is not final-head clearance.
- Subsequent verified operational-status-only main changes use the approved option-A release-batch exception. Functional/source changes still require coordination.
- No merge to main, deploy, cancellation, deletion, force push, rebase, access change, new numerical decision, or denied-comment retry.
