## 2026-11-01 - Full draft CI before promotion / JEG-1466

Contract: Jeremy, Nov 1, 8:29 PM CT: "Let the full required checks run while
it's still a draft, then promote." Keep both bot freshness exceptions false.

### Verified (check named)

- `python3 -m unittest tests.test_draft_full_ci tests.test_draft_ci_workflows
  tests.test_pr_freshness_gate tests.test_preview_workflow_matches_pages
  tests.test_ci_speedup_workflows tests.test_workflow_no_event_interpolation`:
  107 passed. Existing assertions unchanged. The six new tests cover the
  exact-SHA grant, later heads, generic/malformed labels, stale events, closed
  PRs, missing live evidence and grant removal at final verification.
- Before-fix control: running the new module against the previous policy
  produced six expected failures; it cannot authorize the exact-head grant.
- `actionlint -shellcheck= .github/workflows/preview.yml
  .github/workflows/v2-render-test.yml` and `git diff --check` passed.
  Shellcheck is excluded because preview's unchanged clock export has existing
  SC2155; production parity is preserved.
- Additional workflow guards: 52 passed; one extra test module name in that
  invocation did not exist. Corrected event-interpolation module passed in
  the 107-test run above.
- GitHub REST check-runs evidence on `435fa7cd7dc1b33966831e6fef26bf38eaf4e228`
  includes both old deferred and newer workflow suites. A separate dispatch
  cannot erase deferred red/skipped evidence, so this path grants the final
  commit **before pushing**, then runs its first ordinary PR CI in full.
- Only the live `full-ci:<40-character-head-SHA>` label authorizes draft CI.
  Every existing gate/verify call checks it after checking open/current head
  and draft consistency. Existing heavy jobs and required finalizers unchanged.

### Claimed, not confirmed

- Full remote CI, strict promotion and independent review are recorded on the
  ticket after push. No local `make validate` pass claimed: other Mac validate
  processes were already running. No retry loop, self-review, merge, deploy,
  settings/branch-protection, Supabase, credential or HANDOFF.md change.
- Main at preparation is `5381de25a6d6b8356eb799c077d48f5fab9e00dc`, already
  merged into the branch. Recheck ancestry before promotion; no extra catch-up
  needed at preparation. Branch writes stop by Nov 2 5:45 AM CT.
