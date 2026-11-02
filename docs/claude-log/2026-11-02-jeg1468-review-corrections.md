## 2026-11-02 - JEG-1468 org prep review corrections

Contract: address review 5731510694 on draft PR #1274, continuing from
`d7b414fb` on `codex/JEG-1468-org-prep`. Jeremy explicitly requested these
Mac corrections. No merge, deployment, repository settings, transfer,
credentials, Supabase operations, edge-function/CORS edits, or HANDOFF edits.

### Verified (check named)

- `python -m unittest -v tests.test_org_cutover tests.test_llm_surfaces
  tests.test_check_source_fidelity tests.test_health_artifacts_watch
  tests.test_monitor_alerts tests.test_production_verify
  tests.test_github_actions_status tests.test_sync_monitor_fixture
  tests.test_preview_workflow_matches_pages tests.test_draft_ci_workflows
  tests.test_health_artifacts_publish tests.test_live_page_synthetic
  tests.test_fidelity_pulse`: passed, 289 tests; one optional synthetic class
  skipped because this worktree has no rendered-gate Node dependencies.
- `python -m unittest tests.test_pipeline_checkpoints tests.test_verify_live
  tests.test_main_writer_credentials tests.test_main_writer_workflows
  tests.test_ci_speedup_workflows tests.test_health_artifacts_watch_step
  tests.test_health_artifacts_summary_step
  tests.test_waivers_mutation_offline_workflow`: 75 tests passed.
  Both commands used the existing repository Python 3.12 environment.
- New regression checks fail against an isolated archive of `d7b414fb`:
  new-org AI/classic output, monitor links, probes/status identity, workflow
  exports, deploy-status identity, and path/import cleanup. The final output
  assertion passes old/empty slugs on that head and fails the new-org slug.
- `actionlint -shellcheck= -pyflakes=` passed for all 14 changed workflows.
  The lightweight security job runs the identity/output tests even on drafts.
- `git diff --check` passed. GitHub has no inline review threads on #1274;
  corrections are answered in a PR comment linked to the original review.
- `git ls-remote` still reports main at `5381de25` and the PR at `d7b414fb`
  before this push. Main was already merged normally at that main head;
  this correction needs no catch-up merge. `last_rebase` remains unchanged.
- Operational inventory: `make deploy-status` now uses the shared identity.
  `managed-agents/scripts/{lib,create-deployments,idea-session}.sh` and
  `managed-agents/environments/ddf-cloud.yaml` belong to the retired CMA
  runtime (JEG-1173). The scripts refuse to run by default; their historical
  URLs are retained. No retired runtime was restarted or edited.

### Claimed, not confirmed

- Full validation/render and a deployed org cutover are unproven.
  `pgrep -fl "make validate"` showed other active validation processes;
  this run did not start a competing gate or retry a previous one. The
  earlier gate failed for missing Playwright Chromium 1208. Draft CI skips
  heavy build/render jobs and keeps the aggregate checks red.
- A new head requires exact-head CI and an independent delta review before
  promotion. The original COMMENT review is for `d7b414fb` only.
- Separate approval is needed for the edge inventory below. Nothing here
  applies these changes or assumes ownership of datadrivenfootball.com.

### Separately approved edge cutover inventory

- `supabase/functions/get-values/index.ts:24-25`: the `DDF_SITE_ORIGIN`
  fallback is `https://jb-barrel-droid.github.io/fantasy-tools`. A later
  approved function/default or runtime-setting change must point it at the
  confirmed org Pages base (planned `https://datadrivenfootball.github.io/fantasy-tools`).
- `supabase/functions/mcp/index.ts:19-20`: the same independent
  `DDF_SITE_ORIGIN` fallback needs its own approved change.
- `supabase/functions/get-values/index.ts:318-325`: the CORS allowlist has
  `https://jb-barrel-droid.github.io` and the unowned
  `https://datadrivenfootball.com`, but lacks the planned
  `https://datadrivenfootball.github.io`. A separately approved change must
  add the confirmed Pages origin and remove the unowned-domain assumption;
  decide retention of the old Pages origin during transition. The four
  localhost/127.0.0.1 development entries are unaffected. MCP currently uses
  wildcard CORS; no new browser-origin entry is needed there.
- `supabase/functions/usatoday-fetch/index.ts:52`: its ingest user agent
  advertises `https://datadrivenfootball.com`. If this legacy fetcher is kept,
  a separate approved edge change should replace that contact URL with the
  confirmed Pages base. It is not an origin allowlist.

Next turn: once the heavy-test lane is available, run the full gate, obtain
green exact-head CI and an independent delta review. Keep JEG-1468 In Progress;
later org transfer, queue/settings changes, and edge changes need separate
authorization. No product question blocks this correction.

### From Mac follow-through (2026-11-02)

Verified: exact-head failed CI logs were read once; both aggregates failed only
because draft policy set RUN_EXPENSIVE=false and skipped build/shards/render.
Using the canonical repo .venv (Playwright 1.63.0), with RENDER_TESTS_REQUIRED=1:
- 140 tests passed: org cutover, main-writer contracts, CI/draft/preview/shard
  guards, AI connection panel unit/render and full v2 contract render (490s).
- 247 related pipeline/output/probe/v2-builder tests passed.
- actionlint passed all 14 changed workflows; git diff --check passed.
- Promotion catch-up merged origin/main 992c8525 normally, without conflicts;
  its weekly-input-contract tests passed (36 tests). No org-prep code changed.
- GitHub reviewThreads returned an empty list before promotion.
Generated tracked test output was preserved at /tmp/jeg1468-mac-render-generated
and restored to the branch versions; existing untracked outputs were retained.

Claimed, not confirmed: full make validate is left to preview CI; local checks
cover this PR's touched behavior. Full CI and independent Opus delta receipt
must cover the final pushed head before Ready for Release. No merge to main,
deploy, settings, transfer, credentials, Supabase or HANDOFF edits authorized.
