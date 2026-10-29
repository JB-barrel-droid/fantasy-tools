## 2026-10-29 - JEG-1232 saved league-table column order

Contract: build the isolated, keyboard-accessible saved column order for the league trade opportunities table, with a private
Fieldnotes preview, desktop and phone screenshots and tests. Presentation only: no value, source, sort, filter or ranking change.
Table wiring into league.js waits for the coordinated integration with #1072, JEG-1230 and the design-preview owner.

### Verified (check named)

- `python3 -m unittest tests.test_jeg1232_column_order`: 10 model checks in `tests/node/column_order_check.cjs` pass (untouched
  league keeps today's order and stores nothing; catalog covers every `O.OPP_COLUMNS` id with its label; move, save and reload
  through `W.serialize`/`W.parseStored`; boundary announcements; corrupt, legacy and duplicate saved state; required columns
  return beside their baseline neighbour; catalog grows and shrinks; hidden optional column keeps its place; Reset; no input
  mutation and only `ui.columnOrder` changes). Seven mutations of `column-order.js` each make the named checks fail.
- `CHROMIUM_PATH=<chromium 131> python3 -m unittest tests.test_jeg1232_column_order_render`: 6 render checks pass on
  `app/v2-concept/column-order.html` at 1366x900 and 390x844 (keyboard Tab/Enter/Space, focus kept on the pressed button,
  live announcements, aria-disabled end buttons stay focusable, reload keeps the order, header/body edges within 1px in every
  order tried including the grouped Market perception header, header sorting still sorts, hidden/shown, Reset, 44px targets,
  no sideways scroll on the phone, card lines follow the order). A one-off check served a preview whose header ignored the
  saved order: the alignment check reported the misaligned cells.
- `python3 -m unittest tests.test_v2_league_units`: passes (no existing module changed).
- Screenshots: `docs/design/shots/column-order-1366-fieldnotes.png`, `column-order-1366-live.png`, `column-order-390-fieldnotes.png`,
  taken by the render test (`JEG1232_SCREENSHOTS`).
- `app/v2/column-order.js` and `.css` are not in `pipelines/build_v2_page.py`'s copy list, so nothing is published.

### Claimed, not confirmed

- `tests.test_render_sweep_coverage` fails 4 checks on this branch and identically on main without these changes (other render
  modules unlisted in the Makefile); the new render module is wired into `test-render-sweep-2`.
- Local browser: Playwright's own Chromium download was refused, so the render tests ran with a Chromium 131 from the npm
  package `@sparticuz/chromium` via `CHROMIUM_PATH`, plus `--no-sandbox` (root container). CI uses its own browser.
- No Fieldnotes revision was handed over; the preview maps the live `--v2-*` tokens onto the `app/v2-concept/concept.css`
  palette, as the JEG-1233 preview does. Jeremy reviews the design before any public rollout.
- Not wired into league.js yet; the per-unit cell renderers in the preview mirror `renderOpps` for that step.
