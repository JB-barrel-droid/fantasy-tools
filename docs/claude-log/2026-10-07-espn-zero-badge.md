## 2026-10-07 - GAP-025: badge players ESPN projects at 0

Contract: implement Jeremy's GAP-025 decision. Published charts keep their
values as published; players ESPN projects at 0 (injured/out) get a visible
"⊘ ESPN: 0 (out)" badge on the main page (comparison table, chart tooltip) and
on /v2/ (Player values table, tooltip, drawer, Trade targets). No value math
changes. Branch `fix/espn-zero-badge`, not merged.

### What changed
- `product-data.js`: `espn_projects_zero` on each player, from the bake's own
  fields: `espn_status` "ineligible" (ESPN lists the player, projects 0), or an
  ESPN row whose per-game projection is 0 in every scoring. `espn_status`
  "absent" (ESPN has no row) is missing, not 0, and is never flagged. Badge
  copy lives once in `ESPN_ZERO_BADGE`.
- `curve-widget.js`: rows carry `espnProjectsZero`; tooltip shows the badge.
  Only `buildCanonicalMap` and `tooltipHtml` were touched.
- `comparison-dashboard.js`: the old "ESPN Out" badge read the comparison
  artifact's `espn_zeroed` list (4 ids: Achane and three kickers); it now uses
  the player flag (136 rows at default settings).
- `app/v2/targets.js` + `v2.js` + `shell.html`: ESPN-0 players have no ESPN
  value in the engine, so they never had a gap and never appeared in Trade
  targets. They are now listed on the sell side in "ESPN projects 0, but a
  chart still pays" with each chart's value as the engine has it, no gap.

### Verified (check named)
- `tests/test_espn_zero_badge_render.py` (headless system Chrome, real data):
  De'Zhaun Stribling (ESPN ineligible, USA Today 0.8) has the badge in the
  main table, main tooltip, v2 table and v2 drawer; Jonah Coleman
  (FantasyPros 13.6) and Stribling are in the v2 Trade targets ESPN-0 list
  with values equal to `getRows()`; Bauer Sharp (no ESPN row) has no badge
  anywhere; every badged main-table row is in the expected ESPN-0 set; the
  list is hidden on the buy side. Passes.
- Same checks against origin/main's five JS files served in place: 8 errors.
  Against a variant that labels "absent" as 0: 7 errors. (The test's own
  mutation case covers "no flag" and "absent as 0".)
- `getRows()` for all 515 rows, default settings, before (stashed, `make
  sync`) vs after (`make sync`): byte-identical JSON.
- `CHROMIUM_PATH=... make validate`: exit 0. Also passing:
  `test_v2_targets`, `test_v2_targets_render`, `test_build_v2_page`,
  `test_espn_zeroed_staleness`, `test_published_views_render`.
- No horizontal overflow at 390 px on the v2 Trade targets tab (screenshot
  script).

### Claimed, not confirmed
- The v2 chart tooltip badge was checked by reading the code, not headless.
- The premise in the brief that a sell signal ("public chart pays, we say 0")
  already existed is not how the engine works: ESPN-0 players have ESPN
  value null (—), so they never entered the gap math. The new list is the
  sell signal; showing ESPN DDA as 0.0 for them would be a value change and
  is left for Jeremy.
- Achane is no longer priced by any published chart in the current data, so
  he is not one of the test's live examples.
