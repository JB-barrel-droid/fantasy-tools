## 2026-10-08 - Trade targets review fixes (JEG-456 part 1, JEG-458, JEG-459, JEG-461, JEG-464)

Contract: rework the v2 Trade targets tab per the five review tickets (copy, both lists at once with
top-5 collapse, prior-week badge, indexed labelling with an ⓘ, table fits from 1024 px) without
adding value math; every number shown still equals the engine.

### Verified (check named)
- Every rendered value, gap, largest gap and ordering in both lists (25 rows each after "Show all"),
  in opened two-column rows and in phone cards equals the engine's getRows() for ESPN, CBS
  rest-of-season and Razzball: tests/test_v2_targets_render.py `test_rendered_numbers_and_layout`
  (1440 × 900, 1366 × 768, 1024 × 768, 390 × 844).
- JEG-464 copy, no Sell/Buy toggle, no older-week checkbox, top 5 + "Show all N … targets ▾" per list,
  Show all → 25 → Show more → 50 → Show top 5 with the other list untouched, side by side at ≥1280 and
  stacked below, H1 + subtitle + both top 5s above the fold at 1440 × 900 and 1366 × 768, filters on
  one row there, compact two-column rows with a ▾ per row: same test.
- JEG-456 part 1: no sideways table scroll at 1024, 1100 and 1279 px (same checks, run at those widths
  during development; 1024 is in the suite); Pos · Team · Tier sub-line visible.
- JEG-458: "Wk N · indexed" on every chart header, caption "Indexed to our scale", ⓘ beside Compare
  against and in headers: opens the text + How values work link, aria-expanded true/false, Enter opens,
  Esc closes and returns focus, no drawer opened, row order unchanged: same test (`_popover_checks`).
- JEG-459: with FantasyPros simulated on Week 4 it is still compared and carries "Wk 4" with the exact
  label in option, headers, largest-gap attribution, opened rows, cards and footnote; other charts carry
  none: same test (`check_prior`); tests/test_v2_targets.py (prior-week chart compared and flagged).
- 44 px hit areas on every Trade targets control and no horizontal overflow at 390: same test.
- Each check is discriminating: `test_guard_fails_on_broken_builds` (12 mutations across targets.js,
  v2.js, v2.css and the page) fails every one.
- All v2 render suites and test_v2_targets pass (see commit message for the run).
- Screenshots 1440 light/dark, 1366, 1100, 1024 and 390 dark looked right (headless Chromium).

### Claimed, not confirmed
- The prior-week badge was only exercised with a simulated stale source; the fixtures have every chart
  on Week 5, so a real prior-week week has not been seen on this tab.
- Screen-reader announcement of the badge (role=img + aria-label) and the ⓘ dialog was not checked
  with an actual screen reader.
