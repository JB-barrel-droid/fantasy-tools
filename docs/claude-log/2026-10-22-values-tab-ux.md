## 2026-10-22 - Player values tab UX: layout, search, symbols, exact values, player numbers (JEG-926)

Contract: Jeremy's six requests for the v2 Player values tab (2026-10-22): search on the graph,
full-width chart with the table underneath, source symbols on the chart anchored at the left-most
visible player, position selector on the expanded graph, "Set exact values" as a Show-menu item,
all numbers on the player page without clicking "Available". Branch `fe/values-tab-ux`, files
`app/v2/shell.html`, `v2.js`, `v2.css`.

### What changed
- Search: the search box was never in the chart card after JEG-475 (6fcf10e3 moved every control to
  the sticky toolbar). A mirror `#v2PlotSearch` now sits on the graph (top row of `#v2Plot`, so it
  also travels into the expanded dialog) and drives the toolbar box and the same debounce/state.
- Layout: the 1280 px chart-left/table-right grid is gone; `.v2-values-grid` is a plain block at
  every width. The table's internal-scroll max-height now applies from 768 px.
- Symbols: `drawSeriesMarkers` draws each series' publisher symbol (the legend's) at the series'
  first priced player in the shown rows, spread vertically at least 14 px with a leader line when
  moved. Previously nothing was drawn on the chart (the legend glyphs only).
- Expanded graph: `#v2PlotPosition` mirrors the toolbar's Position select; shown only in the
  expanded chart (the toolbar has it otherwise).
- Exact values: `#v2YExact` removed; `Set exact values…` is an option in `#v2Show`. Choosing it
  opens the Value range dialog, leaves Show at its previous value, and the dialog anchors to the
  Show select so Esc returns focus there.
- Player page: every available series shows its number from `row.values` (the engine prices all of
  them); a series not on the chart keeps a small "Add ↗" control under the number.
- `.v2-chart-head` and `.v2-table-head` get `min-height: 44px` so their 44 px card controls sit
  inside the head (the old "Set exact values" button used to set the chart head's height; with the
  table now on screen under the chart the table head's controls overlapped the header row).

### Verified (check named)
- New `tests/test_v2_values_tab_ux_render.py` (1366/1280/1024/390 for layout; 1366 and 390 for the
  rest): passes on the fix; its `test_guard_fails_on_broken_builds` serves v2.js / v2.css with each
  fix reverted (table beside chart, search not forwarded, symbols not drawn, symbols at the right
  end, position hidden when expanded, exact values not in Show, numbers hidden behind Add) and each
  one fails the checks.
- Before screenshots (`~/code/fantasy-tools-selfhost-notes/values-tab-before-*.png`) reproduced
  items 1, 2, 3, 4, 5, 6 headless on origin/main e15bfd53: side-by-side at 1366/1280 (chart 421 px
  wide), 0 markers, no position select in the expanded dialog, `#v2YExact` button, 6 "Available ↗"
  cells with no number on the player page. After screenshots: `values-tab-after-*.png`.
- Suites green with the change (each run alone, `python3 -m unittest tests.<name>`): values_tab_ux,
  chart_height, expand, states, ux, contract, a11y, nav, phone_tap_targets, review_polish,
  chart_zones, chart_fit, customize_pages, ddf, held_pickers, modules, phone_layout,
  phone_nav_overflow, phone_header, phone_rank_overflow, phone_zoom, phone_landscape, name_search,
  values_math_tip, customize_legend, divergence_chip, espn_held_chip, estimated, player_tags,
  disagree, advanced, names, phone_wide_font, phone_fallback_font. `test_v2_panels_render`: the
  behaviour test passed; its guard test failed only on "wide cells scroll sideways" (140 px cells
  fit in the full-width table), mutation widened to 320 px and re-checked with run_checks on
  1440/1366 (caught: 495 px and 248 px horizontal scroll); the whole guard test was not re-run after
  that one-line change.
- Failing identically on origin/main e15bfd53 with this branch's app/v2 changes stashed (so not
  caused here): test_v2_waterfall_render, test_v2_customize_cleanup_render, test_v2_held_chip_render,
  test_v2_nav_320_render ("7 tabs, want 6": the test predates the 7-tab nav),
  test_v2_plain_copy_render (2 guard mutations), test_v2_source_count_render. Not fixed here.

### Old assertions changed (they pinned the removed layout or button), and why
- `test_v2_panels_render`: "at least six table rows above the fold" and its mutation "no
  chart-and-table split" pinned the side-by-side layout Jeremy removed; chart-above-the-fold stays.
  The chart-card control allowlist swapped `v2YExact` for `v2PlotSearch`; the Set exact values
  step selects the Show item instead of clicking the button; the phone check asks for the Show item.
- `test_v2_expand_render`: the "Set exact values is a 44 px control" check and its "small link"
  mutation pinned the removed button; now asserts the item in a 44 px Show menu and no `#v2YExact`.
- `test_v2_chart_height_render`: plot height now excludes the new search row of `#v2Plot`
  (same 280/378 px plot as before).
- `test_v2_states_render`: the drawer cell reader skips the new Add control when reading the number
  (the number itself is still compared to the engine value).

### Claimed, not confirmed
- The 7-tab nav at 390/360/320: covered by test_v2_nav_render and test_v2_phone_nav_overflow_render (green); the CSS here does not touch the nav.
- The dark-theme look of the symbols (halo uses `--v2-surface`) was not screenshotted.
