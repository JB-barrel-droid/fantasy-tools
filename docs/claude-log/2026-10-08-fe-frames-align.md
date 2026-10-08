# 2026-10-08 · v2 front end: built tabs aligned with their Figma frames (task 2)

Frames 05/06 (Risers & fallers), 07/08 + 24 (Compare a trade), 13/14 (player detail), 15/16 (How
values work), 18 (states), plus the short mobile navigation from 02/04/06/08/16. What changed is in
`docs/v2-design-notes.md`, "Aligned with the frames".

## Verified

- `make validate` recipe: exit 0 (includes the new `tests.test_v2_trade_story` in test-core).
- All ten `tests/test_v2_*_render` suites OK, each including its broken-build guard:
  - `test_v2_risers_render` (rewritten for two cards): every listed row's before → after and Δ equal the
    engine's `getPriorWeek` / `getRows` values; an earlier week pair equals `getWeekValues` for both
    weeks. Guards: sign flipped, missing prior read as 0, picked series ignored, earlier pair keeping
    this week's values.
  - `test_v2_offer_render` (new): per-player values on both sides equal the engine's value in the
    picked series or —; side totals equal the engine sum or read incomplete; story kind matches the
    complete rows; the per-player breakdown equals the engine values and the row's net; a chosen player
    stays in search as "✓ Added", disabled; Swap sides swaps; the one-series notice appears. Guards:
    values from the ranking series, total skipping missing players, search hiding chosen players, swap
    no-op, notice never drawn.
  - `test_v2_states_render`: hero and matrix values equal `getRows`; each series in its method's
    column; full screen at 390. Guards: matrix columns out of order, failure leaving values visible,
    empty state never drawn, old bottom sheet instead of full screen.
  - `test_v2_how_render`: weights line and bench share equal `getPositionWeights` / `getBenchShare`;
    Methods row shown. New guard: weights hard-coded.
  - `test_v2_nav_render`: at 390 the five tabs sit on one row. Guard: short-label CSS disabled.
- `tests/test_v2_trade_story.py` (new, pure): `sideTotal` and `tradeStory`, with four mutations caught.
- Manual headless pass on a local `dist/`: screenshots of every changed tab at 1440 and 390, no page
  errors, no horizontal overflow at 390.

## Test assertions changed, and why

- States test: "bottom sheet ≤ 85 %" → "full screen" (frame 14); drawer groups → matrix columns
  (frame 13); the empty state's clear button is now the per-filter "Clear search" (frame 18).
- Nav test: tabs on one row with short labels (frames 02–16); "Add to trade" opens a menu first (frame 13).
- Risers test: reads the two lists instead of one table behind a toggle (frames 05/06).
- How test: mutation anchors follow the new copy ("Source-relative index").

## Decisions made without asking (product-neutral)

- Short tab labels are Values · Targets · Movers · Trade · How (frames say Split and More, which were
  for Market disagreement and a menu that would hold only one item).
- Risers & fallers keeps the Methods row and the Player values filters off (frame 05 shows them; on
  this tab they would change nothing).
- Player detail "See market disagreement" became "See trade targets" (it opens Trade targets searched
  to that player), following the earlier rename of that tab.
- The VORP card's title is "Value over a waiver player" with the pill "VORP vs waivers" (copy rule).

## Claimed, not confirmed

- The Compare story's wording for "split" ("a manager who trades off a source that favors their side is
  the one most likely to accept") is my framing of the job; Jeremy has not reviewed it.
- News in player detail comes from `player-news.json`, last generated 2026-09-20; the date is shown.
- The dropped-series toast after a league change was exercised by reading the code path, not by a test:
  no league setting in today's data drops a selected first-use series.
