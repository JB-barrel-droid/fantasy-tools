## 2026-10-28 - JEG-1189 test-core check: budget-cut bench is identical across sources

Contract: follow-up to JEG-859 (Jeremy picked A+C, 2026-10-27). Add a test-core check that each source's budget-cut bench total (rate[pos|bench] x benchSlice, value-model.js VP-5) equals the shared bench budget pie x W[pos|bench], and so is identical across sources, in every week view the page offers. The role-cut spread (Health check tab) is expected and is not checked. No value change.

### Verified (check named)
- `python3 -m unittest tests.test_bench_budget_cut_render.CheckerTest tests.test_bench_budget_cut_render.EngineTest` passes locally (8 tests): the checker passes identical synthetic runs and fails a 1% perturbation of one source, an unreported zero bench, and a one-source run; the engine (node, worked example, default, expected-starts and bench-share 0.10 variants) passes, and the same engine with source c2's bench groups funded at 101% fails, naming c2 only.
- `python3 -m unittest tests.test_validate_shards` passes: the module is in test-core and in exactly one shard (test-core-shard-3).

### Claimed, not confirmed
- The served-page layer (`ServedPageTest`: four settings, every week view, plus the 101% perturbation served in place of value-model.js) needs Chromium; it is not run locally and relies on PR CI (see the PR's checks).
- `tests.test_render_sweep_coverage` fails on main before this change (test_v2_chart_fullscreen_render, test_v2_consistency_render, test_v2_paste_only_render unwired); not touched here. The new module is wired, so it adds no failure there.
