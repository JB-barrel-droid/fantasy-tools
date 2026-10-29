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

### JEG-1260 correction (same branch)

Base: main `b863069`, merged in normally (no rebase). Paths: `app/v2/trade-readout.js`, an optional `benchLabel` on
`lineup-comparison.js` `renderTable` (default label unchanged, so no live page changes), the JEG-1230 tests.

- Missing players: the 02:56 review fix had not landed on `b0551f5`. Each side now carries `missing`, the union of
  roster and deal players with no value in that view (an outgoing unpriced player counts once); `complete` and the note
  read it. Zero stays a value; null stays missing.
- `out.roster.{mine,theirs}`, independent of any value view: configured bench (league BN, or null), and before/after
  `{size, active, reserve, startingSlots, filledStarting, emptyStarting, bench}`, `rosterSizeDelta`, `benchDelta`,
  `overCapacity`. Starting slots fill by eligibility through `pickStarters` (every player at one value) plus K/DEF slots;
  bench = active players not starting. IR/taxi come from `ValueModel.isReserveSlot` (JEG-1188) when present; without
  it the readout says every non-starter counts. Over capacity is a number and a sentence; nobody is cut.
- Per view `depth.{before,after}`: bench players with a usable value (rosterBalance's `USABLE_MIN` rule). The DDF view
  is shown as DDF replacement depth, the Trade chart average view as market held depth, read from the rows the caller
  passes (the league's own level rows once #1105 lands); no second engine.
- The bench toggle says "Show N bench rows": the aligned before/after row count, not the After bench count.
- `inputFromContext(context, env)`: build's input from JEG-1229's TradeContext (Compare and league-finder shapes), using
  its `dealPartner` and `cacheKey("readout")` when the module is on the page; held sources from `common.sources`.

Verified (JEG-1260):
- `node tests/node/jeg1230_trade_readout_check.cjs`: 315 checks passed (the 263 parity/golden checks unchanged, plus
  52 new). Empty-TE 2-for-1: mine roster 15 → 14 (−1), bench 7 → 5 (−2), TE filled; theirs 16 → 17, bench 7 → 8 of 7,
  over by 1, nobody removed. Outgoing unpriced player counted once; three distinct missing players all counted. 3-for-1
  with an incoming QB under SUPERFLEX. Partly empty roster (no negative bench, null configured bench). IR player held
  off the bench with the slot rule; stated when unknown; unresolved entry keeps its roster spot. DDF and market depth
  per view. A Compare context and a league context for the same deal give the same summary.
- Scratch mutations, each killed: no union (double count), bench counting reserve players, after roster ignoring
  leaving players, DEF slots ignored.
- Fake-DOM run of `renderSide` (scratch only) printed the notes and toggle words that the new rendered test asserts.
- `tests.test_jeg1230_trade_readout`, `tests.test_build_v2_page`, `tests.test_jeg1216_lineup`,
  `tests.test_render_sweep_shards`: OK.
- New rendered test `test_roster_bench_and_missing_counts_are_the_visible_words` (1366 and 390 wide, one and two
  missing players): skipped here (no Chromium); see the PR for the Actions run.

### Claimed, not confirmed

- Route wiring (Compare, then league after #1072, then pair finder after JEG-1219) is follow-up work after owner
  coordination; parity of the live pages is only proven once those hunks land.
