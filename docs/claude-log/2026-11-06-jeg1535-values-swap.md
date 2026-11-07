## 2026-11-06 - JEG-1535 Values swap (Chart, Buy / Sell, Overrides at the root)

Contract: replace the live Values experience (`#player-values`, `#value-overrides`) with the redesigned
`values.html`, published at the site root and fed only by the live engine, with old routes redirecting.
Jeremy (2026-11-06): auto-merge each swap step when all gates pass and an independent review passes.

What changed
- `pipelines/build_root_pages.py` (called by `make sync` after the /next/ preview): writes `dist/values.html` from
  `app/next/values.html` with the v2 front door's engine block injected (engine page body plus scripts and data
  islands, hidden and inert), rewrites links to redesign pages that are not live yet to their live hash routes
  (no public page links into /next/), stamps `?v=<build>`, and turns `dist/next/values.html` into a redirect.
- `app/next/ddf-engine.js`: adapter over `TradeValueCurveControls` (no value math). Storage bridge (plan D4): league
  settings in `ddf.v2.league-settings`, overrides and basis in `ddf-v2-value-overrides` (live format, keyed by
  player_key), shared-link state in `ddf-v2-link-state`, rosters read from `ddf.v2.workspaces`.
- `values-chart.js` / `values-buysell.js` / `values-overrides.js` (extracted from the page): Chart on engine rows
  (DDF Value, indexed charts, projections behind "More sources", value above waivers = mean of the four charts'
  engine `vorp`, risers from `getPriorWeek('ddf_value')`, league settings in Customize); Buy / Sell with Charts =
  mean of listed indexed charts (n/4) and natural fit from `TradeValueFinder.tradeFit`; Overrides with absolute and
  adjustment values, value basis, export/import and the live link format. Inline sample data removed.
- `app/v2/v2.js` (small, additive): `SWAPPED_ROUTES` + `leaveForSwappedPage()` in `canonicalizeHash()`; the route's
  query rides along. Skipped for `navigator.webdriver` unless `?swapped=1`, so the existing v2 render suites keep
  covering the classic views until step 5.

### Verified (check named)
- `tests.test_values_page_engine_parity`: every DDF / CBS / Live market cell on the Chart table equals the engine row
  at 12 settings (standard / half PPR / PPR x 10 / 12 teams x superflex off / on), player set equal, Buy top 5 equal;
  discrimination test fails on a 0.1 drift (lane run, 2 tests pass).
- `tests.test_values_swap_routes`: redirects for `#player-values`, `#value-overrides`, a shared value-context link,
  the /next/ stub, the automation escape, the empty-hash landing, and the storage bridge both ways (9 tests pass).
- `tests.test_build_root_pages`: link rewrite, engine marker, hidden engine, no noindex, stamping, banned copy
  (20 tests pass).
- QA sweep (`scratchpad/qa_values.py`, Chrome, 1440x900 and 390x844, no league and a seeded 12-team league, three
  tabs plus redirects): 0 console errors, 0 page errors, 0 failed requests, 0 horizontal overflow, 0 broken
  same-origin links, 3/3 redirects.
- Buy / Sell lane check: the natural-fit tag, starter changes and Build a Trade link equal an independent
  `tradeFit` call for the selected pair (Playwright, seeded league).

### Claimed, not confirmed
- CI (`make validate`, test-core shards, rendered gate) on the PR head: see the PR checks.
- Live behaviour after deploy: pending `verify_live.py` and a live Playwright pass.
