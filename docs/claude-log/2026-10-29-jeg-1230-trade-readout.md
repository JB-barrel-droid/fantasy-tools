## 2026-10-29 - JEG-1230 shared explicit-trade readout adapter

Contract: one pure readout of an explicit trade that Compare, Find a trade and the league finder can all draw, built only
from finder.js's existing `rosterImpact`/`withChartAverage`/`needLine`/`isNotEvaluated` and drawn by
`lineup-comparison.js`. No route is wired in this PR; numbers, rankings, fit rules and defaults are unchanged.

Base: main `bf0cfee`. Branch `claude/JEG-1230-trade-readout`. Parent JEG-1220 (slice 4).

### What it adds

- `app/v2/trade-readout.js` (`TradeValueReadout`): `build(input)`, `summary(readout)`, `renderSide(readout, who, view)`,
  `sourceStatus(sourceInfo, keys)`, `VIEWS`.
  Input: `{shape, ourKey, chartKeys, sourceInfo, mine: {rows, entries?}, theirs: {rows, entries?}, give: [keys], receive: [keys]}`.
  Views: `ddf` (DDF Value, reads `ourKey`), `market` (Trade chart average, needs `F.MIN_CHARTS` available charts),
  `projections` (DDF Value (projections)). Each view carries status, reason and held sources; each side carries the
  exact `rosterImpact` result, deltas, newly empty slots, the need line, unpriced traded/roster players, K/DEF
  (not evaluated), unresolved roster entries and low-confidence DDF rows.
- Loaded after finder.js and lineup-comparison.js, before league.js and v2.js (`pipelines/build_v2_page.py`).

### Decisions taken (logged in the picks log)

- A traded or roster player with no value in a view: readout is still computed and marked partial (`complete: false`,
  players listed). Routes keep their current gating until wiring (Compare still refuses), so nothing on the page moves.
- A team with no value at all in a view: that team's readout is `null`, never zeros (the pair finder's projections rule).
- A deal key not on the selected roster: not ready, no numbers (Compare's rule).

### Verified (check named)

- `node tests/node/jeg1230_trade_readout_check.cjs`: 263 checks passed. Six explicit deals × Standard/Half/PPR row sets
  (1QB and superflex shapes) give identical before/after lineups, slots, bench, unvalued, empty slots, deltas and need
  lines to copies of the current call paths in v2.js `compareConstructionInput` (DDF), league.js `sidePanel`
  (DDF, market) and finder.js `lineupContext`/`impactBlock` (DDF, market, projections). Deep-frozen inputs, serialised
  before and after: unchanged. Golden fixture `tests/fixtures/jeg1230_trade_readout_golden.json` is generated from the
  route paths, not the adapter (`--write-golden`).
- Named cases in the same script: zero DDF Value counted, null missing; K/DEF reported as not evaluated; unresolved roster
  entry flags partial; empty TE slot reported; too few charts and no charts give an unavailable market with reasons and
  null sides; held projections named; one team without projections gets null while the other keeps its own; deal keys
  outside the rosters give not ready; a custom `ourKey` reads its own series.
- Mutation checks (scratch copies): zeros instead of null for a valueless team fails
  (`one_side_no_projections/standard: finder theirs projections`); market rows without the chart average fails;
  module absent fails.
- `python3 -m unittest tests.test_jeg1230_trade_readout tests.test_build_v2_page tests.test_jeg1216_lineup`: OK.
  Without the build_v2_page change, the load-order test errors.
- `tests.test_render_sweep_shards`: OK. `tests.test_render_sweep_coverage` fails on main too, for three render files
  wired nowhere before this change (`test_interactive_trades_release_render`, `test_v2_compare_rosters_render`,
  `test_v2_finder_guardrails_render`); the new render file is wired.

- Render harness `tests/test_jeg1230_trade_readout_render.py`: the first render sweep on the PR head (run 40812115052,
  shard 1) failed it because the harness was prepended to `body`, where the page hides everything but the app, so the
  bench toggle could not take focus. The harness now sits beside `#v2LgCard` and asserts it is visible. Rerun alone in
  Actions with `RENDER_TESTS_REQUIRED=1` on scratch branch `scratch/jeg1230-render-probe` (run 40814162019): OK at 1366
  and 390 wide (real engine rows equal `rosterImpact`, tables for available views, bench toggle by Enter and Space,
  captions, no page overflow, no page errors).

### Claimed, not confirmed

- Route wiring (Compare, then league after #1072, then pair finder after JEG-1219) is follow-up work after owner
  coordination; parity of the live pages is only proven once those hunks land.
