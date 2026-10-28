## 2026-10-28 - Render sweep: finder K/DEF equality premise and tri-view stale anchor

Contract: get two render-sweep failures on main green without changing product behaviour.
`tests.test_v2_finder_kdef_search_render` ("no trades found without the unpriced entries")
and `tests.test_v2_finder_triview_render.test_guard_fails_on_broken_builds` ("stale anchor
for 'market tooltip without the rescaling'"). Test-only change; no app, dist, fixture or value change.

### Root causes

1. K/DEF search: not data and not the clock. The fixture has not changed since
   e7293965 (2026-10-26 16:16 UTC, all seven sources Week 7). Since week transition A
   (4c17ee6b, JEG-1176) the page prices that fixture the same on the real clock as on the
   pinned one. The test searches the PICK rosters (top 30 by DDF Value, alternating, 12 v 6)
   at the default size, up to 2-for-2. Before e696bf25 the only trade found was a 2-for-1
   (Nabers + Swift for Bijan Robinson). JEG-1108 count balancing (e696bf25, Jeremy 2026-10-26:
   "the throw-in is the supplying team's least valuable bench player") adds their bench player
   to that package, and the charts then reject it. So no 2-for-2 trade is left, and the equality
   check had nothing to compare. The test's premise went stale against a change Jeremy decided.
   While the base run failed, its mutation guards passed for no reason.
   Fix: search up to 3-for-3 (`#v2FindSize` = 3), as `tests.test_v2_finder_render` already does
   for the same PICK rosters. No assertion changed.
2. Tri-view guard: 99e3f5ef (JEG-1081 PR 7) added the anchor
   ``return `${VIEW_TIPS.market} Rescaled to ${name}'s point scale.`;``. In the same PR, the
   fresh-eyes review rewrote the source line so a blend reads "the point scale of X". The anchor
   never matched on main. The test runs only in the render sweep, so nobody saw it. Fix: the
   anchor is now the current `viewTip` line (`MARKET_TIP`). The mutation replaces it with
   `if (id === "market" && custom) return VIEW_TIPS.market;`, which drops the rescaling clause
   as before.

### Verified (check named)

- Python reference (`value_reference.Setting(ppr, 12, hist=History)`, CBS held as
  `_holds.with_pinned_holds`, the test's dist copy) with today 2026-10-28 and 2026-10-26:
  identical rows. Excluded: cbs only (held).
- node `findTrades` on those rows, the PICK rosters, charts usatoday/fantasycalc/fantasypros,
  lineup sanity on. Up to 2-for-2: 1 trade with every finder.js from 9a813b7f to 99e3f5ef,
  0 from e696bf25 to main. Up to 3-for-3 on main: 2 trades.
- `MARKET_TIP` occurs once in `app/v2/finder.js`. In node, `viewTip('market', {mode: 'single',
  label: 'FantasyCalc'})` contains "Rescaled to FantasyCalc's point scale." on main and not on
  the mutant.
- All other anchors in both guards still match the source once.
- `python3 -m unittest tests.test_v2_copy_names tests.test_v2_finder_viable`: OK.

### Claimed, not confirmed

- Both render suites pass in CI. Chromium is not available here, so the render tests were
  not run. The page's real-clock pricing is inferred from the reference and from the unpinned
  tri-view `test_views` passing in the sweep.
- 2 trades at 3-for-3 is a thin premise. A data refresh can empty it again, and
  `test_v2_finder_render` would then fail with it.
