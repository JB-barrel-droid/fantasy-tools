## 2026-10-23 - Player page lists only selected sources, plus a "Show all sources" toggle (JEG-926 follow-up)

Contract: Jeremy, 2026-10-23, after PR #841 (player page showed every series' number with an "Add ↗" link for
unselected ones): "don't show sources on the page that haven't been added via the control charts. Consider a toggle
for add all sources on the player page, but don't just show a source with no number, that is bad UI."
Branch `fe/player-page-sources`, files `app/v2/v2.js`, `app/v2/v2.css`, two tests.

### What changed
- `drawerMatrix` (player page "Source values") is now a list, one row per source: source and week, kind (Our value /
  Rescaled chart / Value above waivers / Our composite for the DDF Value versions), and the number. The old
  publisher-by-method grid would have left blank cells wherever a source was not selected.
- Listed by default: sources selected through Customize / Show (`view.active`, minus legend-hidden series, the same
  rule the table columns use), DDF Value versions included. Every listed row has a number.
- A source with no number for this player gets no row. A selected source that is unavailable for the league or waiting
  on inputs gets a row that says so in one phrase ("Not available for this league", "Waiting on fresh inputs").
  If nothing selected has a number, one sentence says so and points at the toggle.
- "Add ↗" / "Add (older) ↗" links and `.v2-dadd` CSS removed.
- "Show all sources" checkbox (off by default) lists every source that has a number for the player. It is held in a
  variable for the page load only; nothing is written to localStorage or sessionStorage (the test checks both).

### Verified (check named)
- `tests/test_v2_values_tab_ux_render.py` (drawer check, 1366/1280/1024/390): default list equals the selected
  sources with engine numbers; no empty value cell; no Add control; toggle labelled "Show all sources", unchecked;
  turning it on lists exactly the available sources with numbers, matches engine values, leaves storage untouched;
  off again restores the default; a player the engine leaves unpriced for a selected source (DDF Value for Joe Mixon
  in the fixture) has no row for it. Passes on the fix.
- Same drawer check run against origin/main's `v2.js` / `v2.css` (`run_checks` with the old files): fails (6 errors,
  e.g. no toggle, no kind column).
- `test_guard_fails_on_broken_builds`: each of unselected sources listed by default, toggle on by default, toggle
  ignored, a source row with no number is served as a broken build and each is caught. The old "numbers hidden behind
  Add" guard is replaced (its fix no longer exists).
- Other render suites run alone are listed in the PR body.

### Old assertions changed, and why
- `test_v2_values_tab_ux_render` check 6 pinned "every available series shows a number plus an Add control"; the
  2026-10-23 decision reverses that, so it now pins the selected-only list and the toggle.
- `test_v2_states_render` READ_DRAWER read cells by matrix column index and skipped the Add button. The matrix is a
  list now, so it reads each row's kind cell and number cell. The checks are the same: the number equals the engine
  value, the method grouping is right (it now also compares the kind label, so the METHOD_COLUMNS swap guard still
  fails), nothing is listed without a number.

### Claimed, not confirmed
- Dark-theme look of the new rows and toggle was not screenshotted.
- Which legend-hidden series count as "selected" is my reading (hidden on the chart means not listed); Jeremy has
  not ruled on it.
