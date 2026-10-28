## 2026-10-28 - JEG-1142 conflict resolution and regression validation

Contract: preserve the promotion/demotion switch-off for every player, expected
starts and starter/bench weighting; finish PR #1044 against current main.
Jeremy authorized ticket-branch pushes and PR updates. The parent coordinates
merges; no direct main push, PR merge, deploy, production write, or deletion here.
JEG-1205 was not started.

### Verified (check named)

- Read current JEG-1142 and comments (Todo, T1 deep/Bug, no comments), PR #1044
  and its review. No Linear changes. The optional `get_agent_context` tool
  returned `Tool get_agent_context not found`; direct ticket reads worked.
  No `.agents/skills` directory exists in the checkout or fetched main.
- Initial local conflict resolution `f43ac351` integrated PR `dd4b3de2` and
  main `0137a8a7`. Only HANDOFF.md conflicted. A publication dry run rejected
  that old head because Claude independently advanced the shared branch.
  No force push was attempted. All that local work/output remains preserved.
- Final candidate includes shared PR `274f3126`, its contract-helper fix,
  and main `79b9b435` (integration `fc9359cb`). No engine implementation is
  changed from the reviewed shared PR. Only regression guards are strengthened.
- `tests.test_value_pipeline_engine`, `tests.test_spec_reference_value_pipeline`,
  `tests.test_promotion_model_parity`: initial 58-test run passed. The spec
  switch-off test now compares the entire result and all 30 fixture players.
- Negative switch proof: re-enabling each master switch separately produces
  2 JS subtest failures, 1 Python failure and 1 spec failure; restoring all
  switches passes the four switch-off regressions. Temporary JS copy/in-memory
  Python patches only; production switches stay false.
- CI contract failure on `e2dc9da7` was reproduced exactly in a browser:
  Gibbs (2227) was already in the sample [2227,303,3247,2730], so his search
  result was disabled. Adding Bijan (217) then cleared the untouched sample,
  leaving only Receive. Claude's `274f3126` helper selects players outside the
  sample; CT-01, CT-05 and CT-08 all pass, no page errors. Assertions unchanged.
- CI tier-order failure on `274f3126` also reproduced locally. Standard/8 RB
  Wright and McNichols both have exactly 0.0005428869795742036 DDF Value. The
  display sorts tied names alphabetically, while VP-7.3 correctly awards the
  last bench seat by mean PPG (McNichols 4.991818 > Wright 3.975758). The old
  display-prefix assertion was wrong. The correction allows tier order within
  exact value ties, retaining monotonicity across distinct value groups and
  every existing per-player tier/count/zone/value-order check. All 18 composite
  tests pass afterward. Embedded negative cases catch strict inversions,
  mixed-tier groups and a Number.EPSILON difference; a no-op guard fails them.
- Independent review passed the three switch paths, integration, full-result
  spec guard and exact-tie guard. The latter also passed 149,797 exhaustive
  synthetic cases and four edge cases in the independent Node review.
- Core validation completed across recorded runs: 676 unique unittest cases
  plus the Node checks. Initial `make validate` stopped at an older helper
  ignoring CHROMIUM_PATH (2 errors); resumed testing stopped at the invalid
  tier assertion (1 failure), then completed after its correction. This is
  **not** a claim that one uninterrupted `make validate` invocation passed.
- On final main `79b9b435`, `make validate-base` passes (reference, sync, guard
  harness, strict value comparison and integration tests). Strict operational
  comparison: 1,234,991 values across 24 league combinations plus a week-9
  scenario, zero mismatches and page errors. Rank guard: 12 chart/combination
  checks, zero inversions. New-main connector/assist unit checks: 9 passed.
- Final fresh-snapshot focused/baseline tests: 78 passed. Command:
  `python3 -m unittest tests.test_value_pipeline_engine
  tests.test_spec_reference_value_pipeline tests.test_promotion_model_parity
  tests.test_ddf_composite_value tests.test_basis_overrides_render.BasisRenderTest`.
- `node tests/rendered_gate/gate.mjs dist` with the fixture date pinned:
  all 12 shapes passed, zero page errors, every fixed pie sums to 100.0.
  Its self-tests caught both the injected page error and bad pie.
- Direct current spec pipeline vs saved browser dump: 555,750
  value cells and 55,575 source-count cells, zero
  mismatches; max numeric difference 2.42e-13. Source membership,
  allocation, pie, ordered fill sets and row membership agree. This extra check
  excludes prior-week cells, tier labels and some diagnostics.
- The automatic informational `spec_reference.compare` still uses superseded
  ESPN-anchor code. Main already reported 115,229/145,128 mismatches; the
  candidate reports 115,048. It is not the current `value_pipeline.run_week`
  comparator. The direct current-pipeline check above addresses that gap.

### Current snapshot impact

Fixture built 2026-10-28T14:20:11.354412+00:00, pinned date 2026-10-28.
SHA-256: `93067f810cf2f60a0f958d73c1ac9ba21628845445bd37a3560e132ae8b34fbe`. Python reference, PPR/12/1QB, only the
in-memory master switch changes. Expected-start and roster settings stay fixed.

| Player | Promotion on | Promotion off |
| --- | ---: | ---: |
| Brock Bowers | 32.4734 | 33.6782 |
| Bijan Robinson | 71.9407 | 67.8506 |
| Josh Allen | 30.3663 | 31.7744 |
| Tyler Allgeier | 0.2770 | 0.1711 |
| Kenneth Walker III | 71.4334 | 67.3737 |
| Jahmyr Gibbs | 79.2878 | 74.7798 |

Positive DDF rows remain 194 (1QB) and 202 (one superflex). Position-total
changes: 1QB QB +3.56%, RB -1.62%, WR +0.72%, TE +2.00%; superflex QB +2.36%,
RB -2.56%, WR -0.15%, TE +1.24%. These are snapshot calculations, not live checks.

### Claimed, not confirmed

- Current-head remote CI, parent-coordinated merge, Pages publication, live
  `PROMOTION_MODEL_ENABLED = false` verification and USO trade recheck remain.
  No edge-function change or deployment is part of this PR.
- Generated app/dist output remains uncommitted in the worktrees; none was
  deleted for cleanup. Evidence and reproducible scripts live in
  `/workspace/jeg-1142-evidence/` in this environment.

### Environment

Use `CHROMIUM_PATH=/usr/bin/chromium`,
`PLAYWRIGHT_BROWSERS_PATH=/workspace/playwright-browsers`,
`RENDER_TESTS_REQUIRED=1`, and `npm_config_cache=/tmp/jeg-1142-npm-cache`.
The local Playwright browser path aliases the installed Chromium for older
helpers. Browser CDN download was blocked (HTTP 403), including one escalated
retry; no download is needed. The npm cache override fixes this environment's
unwritable default cache. No production credentials or writes were required.
