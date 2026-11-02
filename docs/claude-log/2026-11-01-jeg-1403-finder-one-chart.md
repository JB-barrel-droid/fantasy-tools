## 2026-11-01 - JEG-1403: finder surfaces trades that break even on at least one chart

Contract: apply Jeremy's ruling on JEG-1403 ("I'd still want to see for even one trade chart and then we can use
filters"). The finder's search lists a package you win on DDF Value when at least one available trade chart has the
other side even or better. The shared `MIN_CHARTS` and Compare's `MIN_DEAL_CHARTS` stay 3. This is a gate change, not a
value change.

Change: `SEARCH_MIN_CHARTS = 1` in `app/v2/finder.js`, used only by `findTrades`' default `minCharts` (an explicit
`opts.minCharts` still wins). Copy that stated "3 of 4" now matches: the finder header comment, the pair finder's
no-trades note and the league page intro. Tests that pinned the old rule move to the new one (the rule changed,
Jeremy): `tests/test_v2_finder.py`, the independent judge and weaker-gate mutant in
`tests/node/jeg1188_opportunity_stages.cjs`, and the expected minimum in `tests/test_v2_finder_render.py`. Decision
recorded in `docs/decisions.md`; the math-review agenda item is marked superseded.

### Verified (check named)
- `tests.test_v2_finder`: 1, 2 and 3 of 4 accepting charts list the package and 0 of 4 does not. One priced chart
  that accepts lists it; one that rejects, or no priced chart, does not. An explicit `minCharts: 3` still applies,
  and a held chart can't make up the one. Run against main's `finder.js`, `check()` reports three failures ("1 of 4",
  "2 of 4", "one priced chart"), so the test fails without the change. Mutants "no chart needed" and
  "back to 3 of 4" are caught.
- `test_the_calculator_keeps_its_three_chart_gate`: `MIN_CHARTS` 3, `SEARCH_MIN_CHARTS` 1, `MIN_DEAL_CHARTS` 3. The
  package the finder lists on 1 of 4 charts gets `tooFew` from Compare's `dealRead` on two charts and a market read
  on three.
- `tests.test_jeg1188_opportunity_count`: 7 of 7 pass. The judge now reads the replayed code's own gate, and the
  weaker-gate mutant (`minCharts: -1`) is still caught.
- Discoverable packages on current data. The league page is seeded with the USO journey league (3 charts available;
  CBS held by the test build) and the page's own rows are read (`TradeValueLeague.ui.result`). Main: 5 trades
  league-wide (all 3 of 3 charts fair), 0 send JSN. Branch: 1,594 trades (1,251 at 1 chart fair, 338 at 2, 5 at 3),
  44 send JSN across 8 opponents.
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_uso_site_journey_render`, local Chrome via `CHROMIUM_PATH`.
  Main `951f95df`: 18 run, 3 failed, all at `[league page] [not-discoverable] ... (5 found)`. Branch: 18 run,
  2 failed. `test_guard_fails_on_a_link_without_get` now passes. The other two get past discovery and fail later,
  on Compare (below).
- `make validate` on the branch (pre-merge head `4d29f5cb`, local Chrome): exit 0. `value_check compare --strict`
  agrees: 1,234,507 values, 0 mismatches on every source, so no value moved. The DejaVu Sans phone-font guard passed
  on this run. A first validate run stopped on a 600 s timeout inside `_render_env.ensure_built()` (a sync that
  normally takes 23 s), unrelated to this change; the re-run was clean.
- Two count pins moved because the rule changed. Both were already off on main before this change, and both
  comments record main's own numbers. `tests/test_league_levels_trades.py` `PINNED` (main: (114, 6, 22) for USO
  ddf, ...; branch: (3579, 310, 651), ...) and the `tests/fixtures/finder_search_golden.json` search signature
  (main: 2-for-2 15 trades / 9 groups; branch: 155 / 29).
- Already red on main and unchanged in kind on the branch, not touched here: `tests.test_v2_finder_groups`
  ("the throw-in is not named on the kept trade"), `tests.test_uso_site_journey_contract` (2 failures,
  `basis-changed` on another device), and `tests/node/trade_context_check.cjs` (JEG-1240 envelope TypeError).

### Not fixed here: the league to Compare carry
- With JSN discoverable, `test_journey_keeps_the_trade_context` and `test_unequal_deal_keeps_its_package` reach
  Compare and record `team-substituted`, `gains-missing` and `readout-missing` on league -> Compare and on reload,
  plus `value-changed` and `basis-changed` on another device. Cause: the league row's link
  (`app/v2/league.js` `compareLink`) carries only `give=` and `get=`, so Compare opens its default opponent. No app
  page builds a `tc=` TradeContext transfer on the league route, though `TradeContext.fromLeague` / `toTransfer`
  exist. The link never reads the chart gate, so the gate change doesn't cause this; before it, the 3-chart gate
  hid the stage. Proposed as a child ticket; it may need `app/v2/v2.js` (hot-locked for this job).

### Claimed, not confirmed
- The MCP find-trades tool loads the published `finder.js`, so after deploy it follows the one-chart default too.
  Its description (`supabase/functions/mcp/tools.ts`, mirrored in `docs/values-endpoint.md`) still says "at least
  3 of 4". Not edited here (no Supabase work in this job): it needs its own change and an edge deploy.
- `tools/research/chart_agreement.py` keeps `FINDER_MIN_CHARTS = 3` as the rule its published research used.
