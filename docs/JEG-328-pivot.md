# JEG-328 (item 1) — Pivotable fields for the consolidation watcher

**Branch:** `jeremyburstyn/jeg-328-pivot`
**Commit:** `6216aac`
**File touched:** `modules/consolidation.html` (+434, −1)

## Design decisions

1. **Where the pivot bar lives.** New `.pivot-bar` block placed directly below
   the existing `.filters` block and above the trend view. It is hidden by
   default (`display: none`) and only revealed when the user clicks the new
   **Pivot view** button in `.filter-actions`. Same card style as the existing
   filter bar (reuses `--bg`, `--card`, `--border`, `--muted`, `--accent`)
   so it reads as a continuation of the filter row, not a new page section.

2. **What the pivot bar contains.** Five selectors — Rows, Columns, Values,
   Aggregate, Row limit — laid out in the same `grid-template-columns:
   repeat(auto-fill, minmax(180px, 1fr))` grid the filter bar uses.
   - Rows / Columns: any of the 8 existing dimension fields (`player`,
     `source`, `season`, `week`, `scoring`, `teams`, `qb_variant`, `view`).
     Numeric dims (`season`, `week`, `teams`) sort numerically; strings sort
     alphabetically; nulls always last.
   - Values: only `value` for now (the only numeric column in
     `consolidated_values`). Keeping the Values picker to numeric fields
     keeps the aggregation well-defined and avoids silent NaN coercions of
     `player`/`source` strings. If a future column is added, drop it into
     `PIVOT_MEASURES` and the UI picks it up automatically.
   - Aggregate: mean (default), median, min, max, sum, count, first, last.
   - Row limit: 50 / 100 / 250 (default) / 500 / All. Default 250 matches
     the named use case (pivot player × source for ~5 sources × N players).

3. **Defaults match the named use case.** Rows=`player`, Cols=`source`,
   Values=`value`, Agg=`mean`. Click *Pivot view* with no other filter and
   the user sees the canonical "compare values across sources for every
   player" cross-tab the ticket calls out.

4. **Reuses the live data path.** `renderPivot()` reads from the same
   `filteredRows` array the flat table renders from, which is the same
   array `applyFilters()` populates after the existing filter pipeline
   runs. So:
   - The Supabase live fetch and the JSON-export fallback both feed it
     for free — no new fetch path.
   - All eight existing filters (player search, source, season, week,
     scoring, teams, view, qb) narrow the dataset before pivoting.
   - Sort applied by clicking flat-table headers does **not** leak into
     the pivot output (pivots summarize, so the sort semantics are
     different). Pivot mode gets its own row-dim sort (click the row-dim
     header to toggle direction).

5. **Non-pivot default view is preserved.** `pivotMode` defaults to `false`,
   `pivotBar` defaults to `display: none`, `pivotTableWrap` defaults to
   `display: none`. `populatePivotSelectors()` runs only after `loadData()`
   completes, so the dropdowns are empty during the loading flash. When
   pivot mode is off, `applyFilters()` calls `renderPivot()` but it bails
   on `if (!pivotMode) { … return; }` so the flat table rendering is
   untouched. The Pivot view button label flips between "Pivot view" and
   "Flat view" so the user always knows which is active.

6. **Both views are never shown together.** `togglePivotMode()` hides the
   flat table + pagination when pivot mode is on and shows them when off
   (only after `allRows` is populated, so the empty-state still appears
   correctly when data hasn't loaded yet).

7. **No new build step / no new dependencies.** Everything is vanilla JS
   inside the existing single `<script>` block. No external libraries,
   no bundler changes, no test runner changes.

## What was built

- **CSS additions** (inside the existing `<style>`): `.pivot-bar` + visible
  toggle, `.pivot-bar .filter-group label/select`, `.pivot-bar .pivot-actions`,
  `.pivot-bar .pivot-hint`, pivot table rules (sticky row key, right-aligned
  numeric cells, empty-cell muted styling, yellow "warn" cue on cells that
  aggregated more than one source row, and a `button.toggle-on` style for the
  Pivot view button when active).
- **HTML additions**: Pivot view button in `.filter-actions`, the pivot bar
  block, the pivot table wrap (hidden by default).
- **JS additions**: `PIVOT_DIMENSIONS` (with `numeric: true|false` per field),
  `PIVOT_MEASURES`, `PIVOT_AGGREGATIONS`, six state vars
  (`pivotMode`, `pivotRowDim`, `pivotColDim`, `pivotValDim`, `pivotAgg`,
  `pivotRowLimit`, `pivotSortDir`), `populatePivotSelectors()`,
  `pivotDimMeta()` / `pivotMeasureMeta()`, `pivotCellKey()` (uses a `0x01`
  separator so empty-string row/col values never collide),
  `aggregate()` (mean / median / min / max / sum / count / first / last
  with non-numeric filtering), `compareDimKeys()` (numeric-aware sort),
  `renderPivot()` (header + body, sticky row key, tabular-nums cells,
  tooltips saying "N source rows aggregated as <agg>", rowCount span rewrite
  in pivot mode), `escapeHtml()` / `escapeAttr()` (XSS guard on
  player/source/view strings), `togglePivotMode()`, `btnPivot` and
  `btnPivotReset` onclick handlers, and the per-selector change listener
  that updates pivot state then re-renders. `applyFilters()` now calls
  `renderPivot()` after `renderTable()` so the pivot view is never stale
  when the user toggles into it.

## Commit hash

```
6216aac  JEG-328 (item 1): pivotable fields for consolidation watcher
```

Branch state: `git status` clean on `jeremyburstyn/jeg-328-pivot`. Not
pushed, not merged, not deployed.

## What I could not verify (needs live browser)

I have no way to drive a real browser in this environment, so the
following need a human eyeball before merge:

1. **End-to-end UX.** Click *Pivot view* with default settings — does
   the page actually show the player × source cross-tab with the mean
   `value` in each cell? Cells aggregated from >1 source row should
   appear in yellow (mean/median/sum only).
2. **Filter interaction.** Narrow the player filter to `josh allen`,
   then click *Pivot view* — confirm the row count drops and the pivot
   shows only the matching player. Try also with season/week/scoring/
   teams/view filters.
3. **Aggregation correctness.** Sanity-check one or two pivoted cells
   by hand against the flat table (e.g. josh allen × espn at a known
   week should equal the value in the flat table, not a derived
   number).
4. **Sort toggle.** In the pivot table, click the row-dim header
   ("Player") — confirm the triangle flips and rows re-order.
5. **Reset.** Click *Reset pivot* — confirm the dropdowns snap back to
   player / source / value / mean / 250 and the table re-renders.
6. **Fallback path.** With the Supabase URL temporarily blocked, reload
   the page and confirm the JSON-export fallback still feeds the pivot
   (dataSource badge should say "Fallback: JSON export").
7. **No regression.** With pivot mode off, do all the existing
   operations — search, all 8 filters, header sort, prev/next
   pagination, week-over-week trend, clear filters — still work
   exactly as before?

I *did* static-verify:
- Every new ID referenced by JS is defined in HTML (`pivotBar`,
  `pivotRows`, `pivotCols`, `pivotVals`, `pivotAgg`, `pivotRowLimit`,
  `pivotHint`, `pivotTableWrap`, `pivotTable`, `pivotHeaderRow`,
  `pivotTableBody`, `pivotEmpty`, `btnPivot`, `btnPivotReset`).
- The pivot cell key uses `\u0001` as a separator (verified via
  `cat -A` — byte 0x01) so `rowKey=""` + `colKey="x"` cannot collide
  with `rowKey="x"` + `colKey=""`.
- `populatePivotSelectors()` runs only after data load, so the
  dropdowns are never rendered against undefined data.
- `renderPivot()` early-exits when `pivotMode === false`, so the flat
  table path is not affected.
- The trend view is unchanged; pivot and trend are independent and
  can both be visible.

## Note on file placement

The user's task specified the report path
`/home/hatch/workspace/fantasy-tools/lanes/inbox/minimax/JEG-328-pivot.md`,
but the runtime host blocked cross-workspace writes from this session
(`HOST_CAPABILITY_UNAVAILABLE: this Runtime host cannot prompt for
permission`). The report is therefore committed at
`/home/hatch/workspace/jeg328-pivot/docs/JEG-328-pivot.md` so the
content survives; it needs to be moved to the inbox path on the
reviewer's side before review (or the reviewer can read it from this
branch).

READY-FOR-REVIEW