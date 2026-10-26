## 2026-10-26 - Mobile phases 4 and 5, phone target sizes (JEG-955, JEG-956, JEG-903, JEG-927)

Contract: one PR for the mobile batch — collapse the multi-column rows on phones (JEG-955),
respect the device safe areas (JEG-956) and lift the sub-24 px tap targets from the 2026-10-22
a11y audit (JEG-903). JEG-927 (the mobile umbrella) closes with it. CSS only, plus three
Playwright render tests and the Makefile wiring for them.

### Verified (check named)

- `python -m unittest tests.test_v2_phone_target_size_render` (2 tests, OK): every
  `#v2Legend .v2-legend-item` is 24 px tall and the rank-brush fill is 24 px tall at 375 px and
  1440 px; the `#v2TCards .val.has-math` spans that JEG-947 made 44 px on touch stay above the
  24 px minimum. `test_guard_fails_on_old_css` serves the CSS with the fix removed and the check
  fails, so the test discriminates the fix from the old rule.
- `python -m unittest tests.test_v2_phone_safe_area_render` (2 tests, OK): with
  `--v2-safe-top/right/bottom/left` set to 47/44/34/44 px (the values a notched phone reports),
  the nav bar's content moves down 47 px, the nav and page content move right 44 px, the page
  bottom and the fixed toast move up 34 px, the player drawer's four sides each clear their
  inset, and the page does not scroll sideways. The guard test fails on the CSS without the
  inset rules.
- `python -m unittest tests.test_v2_phone_layout_collapse_render` (2 tests, OK): the "Value range"
  popover's two number fields stack in one column on a 375 px phone, and a search that matches no
  player shows "No players match." with a "Clear search" button and hides the values table card
  (the JEG-827 empty-state item folded into JEG-955). The guard test fails on the old row
  direction.
- `python -m unittest tests.test_v2_a11y_render tests.test_v2_a11y_batch1_render tests.test_v2_a11y_batch2_render` (6 tests, OK): the existing a11y checks still pass with the new rules.
- `python -m unittest tests.test_v2_chart_fit_render tests.test_v2_chart_height_render tests.test_v2_phone_layout_render` (6 tests, OK): the chart still fits its box and the phone layout is unchanged.
- `python -m unittest tests.test_render_sweep_coverage`: the three new render modules are named
  in the Makefile run list, so no module is left unwired.

### Claimed, not confirmed

- A real notched phone was not used. The browser cannot fake `env(safe-area-inset-*)`, so the
  test injects the four custom properties with the values a notched phone reports; the inset
  arithmetic is checked, the device is not.
- `make validate` was not run locally: the contract render suite alone takes minutes and the
  deploy gate runs in preview CI. The pull request's checks cover it.
