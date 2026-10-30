## 2026-10-28 - Pages validation in parallel / JEG-1170

Contract: carry the existing exhaustive preview architecture into Pages as the
first release priority, preserving all validation, rendered gates, publication
artifact identity, and the no-cancellation deployment queue.

### Verified (check named)

- `python3 -m unittest tests.test_validate_shards tests.test_preview_workflow_matches_pages tests.test_deploy_gate_unconditional tests.test_ci_speedup_workflows tests.test_dist_manifest tests.test_render_sweep_shards`: 102 tests pass. Includes mutation coverage for missing/extra/duplicate shards, gate bypasses, setup/commit drift, artifact provenance, and execution of the real deploy success guard against all 16 build/matrix result combinations.
- `/tmp/pages-validation-bin/actionlint .github/workflows/pages.yml .github/workflows/preview.yml` (v1.7.7) and `git diff --check`: pass.
- `pages_problems` rejects the original serial workflow from `origin/main`.
  `recipe_lines` comparison confirms the 96 test-core commands are unchanged;
  `shard_problems` and `validate_problems` confirm the exact existing union.
- Inspection found the coverage/parity/deploy guards previously ran only in
  the informational unit suite. Both build jobs now run them explicitly as
  blocking checks, before building.
- Pages build uploads its checked dist once after all rendered harnesses;
  shards upload nothing. Deploy checks both dependency results and consumes
  the build job's artifact-name output, with no rebuild or shard copy.
- The existing `cancel-in-progress: false`, main push/dispatch triggers, and
  the two warning-only monitoring steps are preserved.

### Claimed, not confirmed

- Full final-head validation is delegated to PR CI, not repeated as a local
  full gate. Independent review and exact CI head/results are recorded on the
  draft PR and Linear ticket after this commit.
- Expected shorter Pages wall time is inferred from the supplied baseline:
  deploy 40703312106 validate 37m35s; preview 40713398220 validate-base 1m29s,
  four exhaustive shards 8m–12m40s, total 13m43s. A successful post-merge Pages
  run must measure the actual change, retain its artifact, and be checked live.
- Parent owns serial merge, Pages deployment and publication/live verification.
  This lane makes no main push, merge, production dispatch, Supabase change,
  rebuild-chain change, writer-pause change, force push or deletion.
