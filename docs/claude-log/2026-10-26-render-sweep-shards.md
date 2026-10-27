## 2026-10-26 - JEG-1117 render sweep split into 3 parallel shards

Contract: per Jeremy's 2026-10-26 decision on JEG-1117 ("Split into 3 parallel jobs (Recommended)"), run the daily render sweep as a matrix of 3 jobs so it finishes under the 60-minute limit (the first scheduled run, 40287913420, was cancelled at the timeout). No production or Supabase change.

### Changes
- Makefile: `test-render-sweep-1/2/3` (16, 16 and 17 modules). `test-render-extra` stays the full list and `test-render-sweep` still runs all of it in one job (local use). Shards are balanced by the per-module times in run 40287913420 (longest-first assignment; about 25 minutes each); the 10 modules that run never reached are assumed 80 s.
- `.github/workflows/render-sweep.yml`: matrix `shard: [1, 2, 3]`, `fail-fast: false`, `timeout-minutes: 60` per job, same Playwright 1.49.1 / `RENDER_TESTS_REQUIRED=1` / `make sync` setup, a per-shard summary (modules run, modules failed, failed names) in `$GITHUB_STEP_SUMMARY`, the warning annotation and a red job on failure. Still `workflow_dispatch` only, same `concurrency`.
- `tests/test_render_sweep_shards.py` (wired in test-unit-modules): fails if a `test-render-extra` module is in no shard, in two shards, or a shard has a module not in `test-render-extra`, and pins the workflow matrix.

### Verified (check named)
- `make -n test-render-sweep-{1,2,3}` give 16 + 16 + 17 = 49 distinct commands, no duplicates, and the set equals the 49 module commands of `make -n test-render-extra`.
- `python3 -m unittest tests.test_render_sweep_shards tests.test_render_sweep_coverage tests.test_run_suite tests.test_validate_runner tests.test_preview_workflow_matches_pages tests.test_monitoring_coverage tests.test_gha_schedules_pg_cron`: 74 tests OK. No existing expectation was changed; none pinned the rule Jeremy changed (the job id `render-sweep` and file name are unchanged).
- The shard test's own negative cases fail on a module dropped from every shard, a module in two shards, and a module only in a shard.
- Shard command shape: `tests/run_suite.py` on a one-target Makefile holding the smallest module (`tests.test_v2_all_projections_paused_render`) exited 0 (3 tests OK).

### Claimed, not confirmed
- Shard wall time (about 25 minutes of tests plus setup) is an estimate from run 40287913420's per-module times, not a measured run; see the PR for the dispatch result.
- The 10 modules the cancelled run never reached are assumed 80 s each.
- Several modules failed in run 40287913420 (customize_cleanup, customize_pages, divergence_chip, values_tab_ux, finder_box/chips/collapse/eval/fit/groups/impact/kdef_search); those are unchanged here and will show as failed modules in the shard summaries.
