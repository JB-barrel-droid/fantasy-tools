## 2026-10-29 - JEG-1232 league trade cards: one line per column, fixed order

Contract (revised Oct 29): Jeremy reviewed a private before/after phone preview, approved Our fit and Their fit on separate lines, and
called the Up/Down column order list "an odd ui to present users". He then picked a fixed order, value first, with no picker and no
saved per-league order. So the column order model, control, private preview and their tests from the first commit are removed, and the
live phone card in `app/v2/league.js` `renderOpps` draws one line per table column in the table's order: trade, DDF Value, projections,
Our fit, Market, Their fit. Presentation only: no value, source, sort, filter or ranking change; the desktop table is unchanged.

### Verified (check named)

- `CHROMIUM_PATH=<chromium 131> python3 -m unittest tests.test_v2_league_phone_render`: the new `check_card_lines` passes at 390 px on
  the 4-team fixture (every card's lines carry `data-line` in the order above, the Our fit line holds no Their fit text, the Their fit
  line exists), and `test_guard_fails_on_broken_builds` passes, including the new mutation that puts both fits back on one line, which
  the check names ("Our fit line").
- `python3 -m unittest tests.test_v2_league_oppanel_render tests.test_v2_league_tables_render`: pass.
- `python3 -m unittest tests.test_v2_league_units`: passes. `node --check app/v2/league.js`: ok.

### Claimed, not confirmed

- `test_phone_contrast_keyboard` fails locally on its 44 px check (20x20 checkboxes in `#v2LgOpps`), and fails the same way on
  origin/main d1d108c without this change, so it predates this PR.
- Local browser: Chromium 131 from the npm package `@sparticuz/chromium` via `CHROMIUM_PATH`; CI uses its own browser.
- The private phone preview Jeremy reviewed was a claude.ai page with sample rows, not this build.
