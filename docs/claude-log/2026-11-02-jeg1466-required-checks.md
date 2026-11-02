## 2026-11-02 - Required-check completeness / JEG-1466

Contract: fix review P1 on PR #1262 at `28d44533`, diagnose its two CI reds,
and return a green head for independent delta review. Jeremy's ruling stays:
full required CI runs while draft; promotion follows green exact-head checks.

### Verified (check named)

- Before implementation, `RENDER_TESTS_REQUIRED=1 .venv/bin/python -m unittest
  tests.test_pr_freshness_gate.FreshnessTest.test_green_subset_never_authorizes_missing_required_checks`
  failed in all four subcases: a lone green security, informational, preview
  or render check incorrectly returned 0. The same regression passes in the
  focused run below after the fix.
- `RENDER_TESTS_REQUIRED=1 .venv/bin/python -m unittest
  tests.test_pr_freshness_gate tests.test_draft_ci_workflows
  tests.test_draft_full_ci tests.test_preview_workflow_matches_pages
  tests.test_ci_speedup_workflows tests.test_waivers_mutation_offline_workflow
  tests.test_workflow_no_event_interpolation`: 130 passed. Existing assertions
  remain; positive fixtures now supply both required finalizers. Added cases
  cover partial registration, pending completion, neutral/path-skip refusals,
  producing app, manual/status substitutions and both promotion entry points.
- The gate's reviewed policy requires `preview` and `v2-render` success from
  GitHub Actions on the exact head, independent of registered rows or caller
  config. Missing required jobs have no path exemption. Supplementary checks
  retain their existing strict pending/red and explicit path-skip rules.
- `gh` REST reads of runs 41391154835 and 41391154761 were rate-limited.
  Connector log fallback read the jobs without changing or rerunning them.
  Preview pr-state job 125102692166 at 04:57:05.870 UTC and render pr-state
  job 125102667388 at 04:56:59.141 UTC both report **PR draft state changed
  since this event; full verification cannot pass**. Their finalizers
  (125102871211 and 125102840167) show `RUN_EXPENSIVE=false` and skipped
  build/shard/render jobs. This is lifecycle refusal, not flaky test evidence
  or a main baseline failure. Keep this fix's head draft and grant its exact
  SHA before the first push; never toggle draft while its CI runs.
- GraphQL review threads contain one inline P1 (4439053678); the independent
  review adds the CI-red blocker and no nits. Both are addressed by this fix
  and the lifecycle correction; external call sites remain inventoried in
  the original log, without writes outside the approved checkout.
- `pgrep -fl "make validate"` found another validation (PID 62269), so no
  competing local validate/render suite was started. More than 5 GiB free.

### Claimed, not confirmed

- Final head, remote full CI, current-main ancestry and promotion are recorded
  on the ticket/PR after push. No independent review pass is claimed here.
- No merge, deploy, Supabase, credential, settings, force-push or HANDOFF.md
  edit. Both bot freshness exception flags remain false.
