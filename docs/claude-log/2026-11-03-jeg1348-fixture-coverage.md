## 2026-11-03 — JEG-1348 fixture and usability continuation

Contract: continue PR #1292 on its existing branch, improve independent
end-to-end fixture/usability evidence, and make the held integration locally
reviewable. Preserve valuation and #1290's ownership of `v2.js`.

### Verified (check named)

- Resume reconciliation: remote #1292 still pointed at `febd74e1`; only the
  previous generated build output was dirty, and no Python/git/gh work was
  running. #1290 remains open at `04e124f7` and owns `v2.js`. Existing ticket
  comments show no other claimant. No uncertain write or duplicate PR was found.
- Normal merge of `origin/main` at `ad0cfc3a` is clean. That includes the
  independently owned #1287 stability negative-control repair. Existing local
  generated output was retained and stays excluded from this PR's changes.
- `tests.test_jeg1348_bench_context`: 6 tests pass. The new eight-scenario
  fixture's bye counts are independently checked against the committed
  schedule; it includes season, regular, custom short regular, playoffs,
  completed regular season, one remaining week, and empty weeks 17/18.
- A new regression fails before the metadata guard: the formatter returned
  rate tables for all three cases with missing seasons, team count or basis.
  It now refuses those incomplete cohorts, retaining the unavailable state.
  No rates or sample counts were changed or extrapolated.
- Browser checks read every position/depth cell, count, caption and row/column
  header against the committed O3 research matrix rather than using the
  display asset as their oracle. Historical cohorts remain fixed when the
  current league switches to 8 teams / Standard scoring. Missing asset and
  missing bye-map browser paths pass without inventing zero values.
- The visible Regular season control changes the measured readout and survives
  reload. Enter/Space operate the historical disclosure with focus retained;
  Escape closes the panel and returns focus to the context menu. Focused
  usability/export rerun: 2 tests pass (23.2s). The initial Escape assertion
  expected node removal; the corrected new assertion checks visibility,
  matching the existing panel's behavior.
- The final versions of both focused modules pass together inside the normal
  `make validate` target: 14 tests (6 data/provenance + 8 browser) in 45.3s.
  This includes waiting for both engine and front-end readiness on reload,
  and checking the 320px disclosure stays within the visible viewport. The
  unchanged bench-share reference suite also passes (3 tests, 38.0s).
- `tools/preview_bench_context.py` exports the actual patched builder output
  and assets to a new local directory, pins the fixture clock and records the
  integration-patch/matrix hashes. Its browser check serves the export at
  320px without response overrides, verifies the table fits, and confirms both
  protected source files are byte-identical before/after export.
- The held integration patch still passes `git apply --check`; the real
  `app/v2/v2.js` and `pipelines/build_v2_page.py` remain identical to current
  main. Source changes since the prior implementation are confined to the
  display module's missing-metadata guard, fixtures/tests, and the review tool.
- Compatibility check against #1290's exact current head `04e124f7`: fetch its
  v2.js patch, apply it only to a temporary copy, then run `git apply --check`
  for the held JEG-1348 patch. Both patches apply cleanly in that order. A
  refreshed PR metadata read confirms #1290 remains open at that same head.
- Complete `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make
  validate` returned exit 0. The recovered log/report confirms strict
  engine/reference agreement on 1,234,507 values across 25 settings, zero
  page errors, and all 170 hermetic integration tests passing. No finished
  validation was rerun after the interruption.
- Execution transport disconnected immediately after that successful exit.
  GitHub recovery uploads were blocked before execution; the existing PR
  stayed at `febd74e1`, with no new tree, commit or ref update. Jeremy then
  explicitly approved publishing these recovered code/tests/fixture/tool/docs
  to the existing public PR branch: "Yes, you don't have to ask" (parent
  thread transcript, 2026-11-03). The runtime recovered with the original
  files and log intact; their 80/107/245 code/test line totals match the saved
  diff. Publication uses those original validated files, not reconstructed
  replacements. The interrupted Linear handoff marker was absent, so no
  duplicate post was made.
- Latest main `c5bc459f` differs from validated base `ad0cfc3a` only in five
  operational status JSON files. The validated source base is retained;
  no status-only catch-up or repeated broad validation was added.

### Local review

Use a new output directory:

```sh
CHROMIUM_PATH=/usr/bin/chromium python3 tools/preview_bench_context.py --out /tmp/jeg1348-review
python3 -m http.server 8765 --directory /tmp/jeg1348-review
```

Open `http://localhost:8765`, then context menu → Position weights. Review
the measured line and expand Historical breakout odds. Your league → Optimize
for → Regular season changes the window; reload retains it. The export is a
fixture review copy with the held patch applied; the live/shared sources stay
unchanged. The original integration patch remains the coordinator's handoff.

### Claimed, not confirmed

- Exact-head ordinary CI is pending publication. The coordinator authorized
  readiness for CI when appropriate; AGENTS.md's eight-ready-PR cap was full
  at the last queue check. There is no
  independent review, merge, deploy or live-activation claim.
- The earlier dependency-edit denial is preserved. The request to replace
  JEG-1348's blocked-by links was not retried, altered or performed indirectly.
  Integration/wording/high-risk review ownership stays with the coordinator.
