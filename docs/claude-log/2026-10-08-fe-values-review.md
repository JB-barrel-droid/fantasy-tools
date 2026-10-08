# 2026-10-08 fe-values (Player values layout: JEG-470 / 472 / 473 / 475)

Lane: app/v2 (shell.html, v2.js, v2.css), tests/test_v2_*, docs. No engine, data or workflow file changed.
v2 still does no value math; the only new comparison is the presentational heat tint (two shown values, colour only).

## Verified (check named)

- Toolbar: Search · Position · Show · Rank by · Δ · More · Reset each once, left to right, sticky; chart options,
  rank-window buttons, Reset to all / Reset zoom / Clear filters / Value range button gone; only brushes and zoom
  inside the chart (`test_v2_panels_render.check_toolbar`).
- Show Top 25 / Starters / Bench / Waiver against `getZones()`; table rows follow (`check_toolbar`).
- X brush mouse drag → Show "Custom lo–hi"; More From 20 To 60 → window 20–60, first row 20 (`check_x_brush`).
- Y brush: vertical labelled ranges with "Value x.x"; mouse drag and PageDown / arrows; 12–30 keeps only ranking
  values in 12–30 AND ranks in the Top 50 window; thumb labels; omitted count for a series with missing values;
  "Set exact values" names its basis and refuses min > max (`check_y_brush`).
- Reset restores search, position ALL, Show Top 100, range, sort, Δ (`check_reset`).
- Columns menu hides a method group but not the ranking series; Team off drops it from the player line (`check_columns`).
- Table fit at 1440 × 900 and 1366 × 768: no sideways scroll, headers ≤ 2 lines, group row matches each series'
  method, sticky header (stays put when the body scrolls) and Player column, rows ≤ 37 px, numbers one decimal /
  right / 6–8 px padding, heat direction = shown values and named in the title, "—" has a reason (`check_table_fit`).
- Above the fold: chart card bottom 817 / 900 and 761 / 768; 9 and 6 rows visible; h1 26–28 px; value line names
  the engine week (`check_fold`).
- Guard: 16 mutations (13 JS, 3 CSS) each fail the checks (`test_guard_fails_on_broken_builds`).
- All v2 render suites pass after `mk.sh sync` (a11y, compare, how, nav, offer, panels, risers, share, states,
  targets, ux, weight). states / ux were rerun after two fixes (empty state hides #v2Chart; Player sort button 44 px wide).
- Screenshots 1440, 1366, 820, 390 in light and dark: no page overflow, no page errors.

## Claimed, not verified

- Real touch dragging of the vertical Y brush on a phone (it is hidden below 768 px by design; tablets untested on device).
- Firefox: the vertical range uses `writing-mode: vertical-lr; direction: rtl` (Chrome 124+, Firefox supports it too) —
  only Chromium was run.
- 1280 × 800: no sideways scroll measured, but the chart card ends at ~812 px (not a ticket target).

## Changed rules (tests updated because the ticket changed them)

- panels: chart options / navigator / value range checks replaced by toolbar, brush, reset, columns, table-fit and fold checks.
- states: "Clear filters" fallback clicks the new Reset.
- ux: the "40 px rank-window buttons" mutation became "40 px zoom buttons" (the rank-window buttons are gone).
