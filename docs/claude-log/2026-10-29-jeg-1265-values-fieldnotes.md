## 2026-10-29 - Values page Fieldnotes presentation, isolated component (JEG-1265, part of JEG-1192)

Contract: build the Values page (Value chart) table and controls in the Fieldnotes direction as an isolated component with
current-contract fixtures and parity tests, without touching v2.js, v2.css, league.js, the engine, the Makefile, shared
tokens or navigation. Runtime integration waits on JEG-1137 and goes to its owner as the plan below.

New paths (nothing loaded by the page):
- `app/v2/values-fieldnotes.js`: `sortRows` / `nextSort` / `ariaSort` (copies of the page's sort contract), pure `viewModel(ctx)`,
  `render`, `mount` with focus kept across re-renders. States: loading, unavailable, mixed (weekly beside rest of season is
  withheld), empty, ready.
- `app/v2/values-fieldnotes.css`: scoped to `.values-fieldnotes`; only shared `--ddf-*` / `--v2-*` tokens and the shared type
  scale; warm paper is the existing `:root[data-canvas="paper"]` opt-in. Table at 720px and up, one card per player below,
  every other value behind an "All values" disclosure, grouped as the table is.
- `tests/fixtures/values-fieldnotes/synthetic-values.json`: 30 labelled synthetic players; populated, a finite 0, missing
  cells with reasons, an unavailable source column, a long name, cell notes. No source dates or freshness.
- `tests/values_fieldnotes_harness.cjs` + `tests/test_jeg1265_values_fieldnotes.py`: parity and state checks, 18 mutation proofs.
- `tests/test_jeg1265_values_fieldnotes_render.py`: real browser at 1280, 390, 320 on a private harness page with a mocked
  controller (test scaffolding, not the live hookup).
- `.github/workflows/jeg1265-values-fieldnotes.yml` (+ one `unmonitored_workflows` line in `config/monitoring_coverage.json`):
  runs both tests on PRs touching these paths and keeps the screenshots as a run artifact.

What is reused, not redefined: number format is v2.js `fmt()`; sort is v2.js `sortedRows()` and its header click rule; group
order and labels are `TABLE_GROUPS`; group notes are `SERIES_GROUPS` notes; source kinds come from `source-views.js`
(JEG-1212). The page keeps filtering (`view.visible`), the Rank by choice, value basis, Show, value range and every state.
The existing chart card is unchanged and stays where it is (pick logged in the picks log).

### Verified (check named)
- `python3 -m unittest -v tests.test_jeg1265_values_fieldnotes` (cloud session): 3 tests OK; harness 17/17 checks pass,
  including fmt, sortedRows (every column, both directions, rank-order and reversed input), header click and aria-sort read
  out of v2.js itself; all 18 mutations are caught by the named check.
- `tests.test_monitoring_coverage tests.test_vintage_trigger tests.test_workflow_script_paths tests.test_ci_speedup_workflows
  tests.test_deploy_gate_unconditional tests.test_launch_copy_guard tests.test_v2_copy_names tests.test_v2_tokens`: OK with the
  new workflow and files.
- jsdom smoke (scratch, not committed): mount, sort keeps focus, search keeps focus, empty then Clear returns focus to the
  title, position filter, Rank by, Show more, Details callback, missing reason and 0.0, loading / unavailable / mixed.

- CI run 40915263348 (head dddb3e9), render test: 7 failures, three causes, fixed in the next commit. (1) Desktop page
  scrolled sideways (1357 > 1280): the table's absolutely placed screen-reader text escaped the scrolling wrapper; the
  wrapper is now `position: relative`. (2) Focus fell to the page body when the title had focus and the component
  redrew; it now returns to the title. (3) The test's expected number used Python rounding (70.25 -> 70.2); the page's
  `toFixed` gives 70.3, which the component showed. The test now rounds as `toFixed` does (5,237 values compared, 0 differ).
- After merging main (JEG-1137 foundation, fc70923): headings now read the shared `--ddf-font-headline`, and the render
  harness opts into `data-design="fieldnotes"`.

### Claimed, not confirmed
- The render test was not run in this session: the cloud container has no browser and browser downloads are disabled
  here. It runs in the new workflow with `RENDER_TESTS_REQUIRED=1`; its result and screenshots are on the PR and the ticket.
- `make validate` and the contract render test were not run; no loaded file changed.

## Correction JEG-1299 (review of bea8ab96): phone Details focus

Finding (P2): the table row and the phone card each have a Details button, and both carried `data-focus="open:<key>"`.
`update()` took the first match, the table's, which is `display: none` at 719px and below, so on a phone focus was lost
after any redraw.

Fix: each presentation has its own focus id (`open:table:<key>`, `open:card:<key>`). `update()` focuses the visible
match, falls back to the same player's button in the other presentation when a resize hid it, and goes to the title
when nothing visible matches or focus did not land. No values, data contracts, sorting or runtime integration changed.

### Verified (check named)
- `tests.test_jeg1265_values_fieldnotes`: 3 OK here (17/17 harness checks, 18/18 mutants).
- Failing before: the new render regressions ran in CI on tests-only commits against the unchanged component
  (run 40947876817 on 3373fd5): redraw and drawer return at 390 and 320 failed with focus on BODY (4 failures);
  1280 and the title fallback passed.
- Passing after: the same job on the fix commit (run id on JEG-1299).

### Claimed, not confirmed
- The render tests were not run in this session (no browser here); CI's `values-fieldnotes` job runs them with
  `RENDER_TESTS_REQUIRED=1`.

## Integration plan for the JEG-1137 owner (not applied here)

1. `shell.html`: add `<link rel="stylesheet" href="v2/values-fieldnotes.css">` after `v2.css`, and
   `<script src="v2/values-fieldnotes.js"></script>` after `source-views.js` and before `v2.js`. Add
   `<main class="v2-wrap" id="v2ValuesFieldnotes" hidden aria-labelledby="vfTitle"></main>` beside `#v2Main`.
2. Build registration: list both files wherever the sync / Pages build copies `app/v2` assets (`make sync`), if it lists files.
3. `v2.js`, one hunk beside `renderTable()` (hot file, one ticket at a time). The context is read from what the page already has:
   ```js
   function valuesFieldnotesContext() {
     if (!view) return {status: "loading"};
     const cols = tableColumns();
     return {status: "ready", title: "Value chart", lede: $("v2ValueLine").textContent,
       settings: /* the league settings line the page already shows */, basis: {label: /* basis name */, text: $("v2Main").querySelector("[data-basis-ours]").textContent},
       rankKey: view.rankKey, rankOptions: /* the entries renderSeriesPicker gets, with groupSeriesName labels */,
       groups: TABLE_GROUPS.map(([id, label]) => ({id, label, note: (SERIES_GROUPS.find(g => g.id === ({projections: "proj", published: "pub"}[id] || id)) || {}).note || ""})),
       columns: cols.map(col => ({id: col.id, label: col.source ? (PLAIN_NAMES[sourceMeta(col.source).publisher] || col.label) : col.label,
         method: col.source ? METHOD_LABEL[sourceMeta(col.source).method] || "" : col.id === "spread" ? "of our values" : "",
         kind: col.id === "rank" ? "rank" : col.id === "name" ? "name" : col.id === "spread" ? "spread" : col.source ? "value" : "meta",
         text: Boolean(col.text), order: Boolean(col.order), source: col.source || null, group: col.group || null,
         unavailable: col.source && view.infoByKey[col.source] && !view.infoByKey[col.source].available ? missingReason(col.source, null) : null})),
       rows: view.visible.map(row => ({player_key: row.player_key, rank: row.rank, name: row.name, pos: row.pos, team: row.team,
         tier: valuesTier(row), tierOrder: TIER_ORDER[tierFor(row, view.rankKey, view.tierScope)] ?? 3, values: row.values,
         spread: /* the spread column's get(row) */, reasons: /* missingReason(key, row) for each missing cell, plus the spread reason */,
         notes: /* the badge texts appendLowConfidence / appendOverrideFlag already add */})),
       sort: state.sort, shown: state.shown, window: state.window, filters: {search: state.search, position: $("v2Position").value},
       positions: [...$("v2Position").options].map(o => ({value: o.value, label: o.textContent}))};
   }
   ```
   Mount once with `on`: `sort: next => { state.sort = next; render(); }`, `filter: change => ` the existing search /
   position handlers, `rankBy:` the existing Rank by change handler, `showMore:` the existing Show more handler,
   `open: key => openDrawer(view.visible.find(r => String(r.player_key) === key))`, `clear:` the existing Clear all filters.
   Call `handle.update()` wherever `renderTable()` is called. Horizon: pass `horizon` per column only once weekly values
   appear on this page; until then leave it unset.
4. Rollout switch: show `#v2ValuesFieldnotes` in place of the toolbar and table card behind the JEG-1209 private-preview
   gate only; public rollout waits on the JEG-1209 design review and copy gates. Keep the chart card, its brushes and the
   drawer as they are.
5. Tokens: done. The JEG-1137 foundation on main added `--ddf-font-headline`; headings read it, so they are Fraunces under
   `:root[data-design="fieldnotes"]` and the UI face without it. The render harness sets that opt-in. No token is defined
   locally.
6. Gate: `tests.test_jeg1265_values_fieldnotes` stays as is; turn `test_page_does_not_load_it_yet` into a check that the
   page loads it, and add a contract render test on the real page comparing the component's cells to `#v2Table` cell text
   for the default and one sorted state.

## 2026-10-30 - Codex review finding (P2): phone sort controls

Finding on head 2bab589: at 719px and below the table headers are hidden, so phones had no way to change the sort.
Fix: a phone-only "Sort by" select and an order button above the cards (hidden at 720px and up). Both hand on the
header's own `next` sort (`nextSort`, the page's click rule), so a phone sort is exactly a header click: picking a column
gives its first-click direction (A to Z for text, highest first otherwise), and the order button reverses the active
column. The rank column is not offered, as it has no header button. No new sort rule, math or contract.

### Verified (check named)
- jsdom smoke (scratch): Sort by starts on the ranking series; Player gives name asc, then the order button gives desc;
  ESPN equals the header's `next`; reversing the default gives the ranking series ascending; focus stays on each control.
- `tests.test_jeg1265_values_fieldnotes` OK (17/17 checks, 18/18 mutations), plus monitoring coverage and v2 tokens.

### Claimed, not confirmed
- New render test `test_phone_sort_matches_header_sort` (320 and 390, card order equals the desktop header-click order,
  focus kept, missing sorts last, layout fits) runs in the PR workflow; this container has no browser.
