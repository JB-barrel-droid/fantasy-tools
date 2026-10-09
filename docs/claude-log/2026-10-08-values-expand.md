## 2026-10-08 - Player values: expand chart and table, Reset zoom, filter chips (JEG-483, fe/values-expand)

Contract (Jeremy approved all four items; the above-the-fold layout from 6fcf10e3 stays):
1. Expand chart (⤢): a large dialog on desktop, full screen below 768 px, with a ~75vh plot, both brushes,
   25 / 50 / 100 / All, axis zoom and the legend. State is shared with the toolbar. Player names stay on the
   points when zoomed.
2. Expand table: full height, with Pos / Team / Tier as their own sortable columns, sticky header, heat tint
   and Show more.
3. Reset zoom: shown only while zoomed; it returns to the Show preset from before the zoom.
4. Active filter chips, each clearing only its own filter; "Set exact values" as a 44 px control.

### How it is built
- One overlay, `#v2Expand`, inside `#v2Main`. Opening it moves the live `#v2Plot` (or `#v2TableWrap`) node into
  the overlay and leaves a placeholder of the same height; closing it moves the node back. The page keeps one
  chart, one pair of brushes, one table and one state, so a brush in the expanded view is the toolbar's brush by
  construction. `renderCharts()` (or `renderTable()`) runs on open, close and resize.
- Zoom memory: `state.zoomFrom` (the preset before Custom) and `state.rankZoom` (whether the rank window itself was
  zoomed, as opposed to only the value range).
- Tier: after the rebase onto 313cb72e the branch's own `tierOf` was dropped for the shared `tierFor` / `tierText`
  (Trade targets); the expanded table's Tier column sorts by it. Earlier draft: `tierOf(row)` (`row.ddfTier` for DDF Value, else `getZones()` against
  `row.fullRank`), used by the Player values table, the expanded table and the chart tooltip.

### Verified
After rebasing onto origin/main 2526eefd, every tests/test_v2_*_render.py passes, as does tests.test_launch_front_door.
`scripts/validate.py` passed 58/58 before the rebase. After the rebase, one run failed in
test_main_table_engine_parity ("product-data.js missing", main page, not v2); that test alone and a full validate rerun (60/60) passed.
`tests/test_v2_expand_render.py` checks against the engine:
- the expanded chart's lines (data-source set) equal the main chart's;
- the plotted rows equal the engine's rows for the rank window and value range;
- each line's first and last points sit at the engine's `row.values`, with and without axis zoom;
- Esc closes each view and focus returns to its button;
- the expanded table's Pos / Team / Tier equal the engine rows, both ranked by DDF Value and by another series;
- Reset zoom restores the prior preset (Top 50 after a zoom, Top 25 after a Y brush) and keeps the search;
- each chip clears only its own filter;
- "Set exact values" is at least 44 px;
- there is no overflow at 390 and both views are full screen there.

Each of the nine broken builds fails the checks.
Screenshots at 1440 and 390 were checked by eye: the default view, the chips, the expanded Top 25 with names
staggered, axis zoom 12–30 and the expanded table.

### Claimed (not verified)
- Dark mode was not looked at. The overlay uses the existing tokens, plus the same rgba scrim as `.v2-scrim`.
- Not pushed: the coordinator held pushes while main deploys fail on the fe/ddf defaults (test_ddf_composite_value).
- Above-the-fold row counts at 1366 × 768 come from `test_v2_panels_render`'s existing check only.
  "Set exact values" now takes the last line of the chart card head, which can add one line when the legend is long.
