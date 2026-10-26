## 2026-10-26 - JEG-1090 league phone sort selector overflowed 320 px

Contract: find and fix the sideways scroll `tests/test_v2_league_phone_render.py::test_phone_contrast_keyboard` reports at 320 px on clean main, with the test as the proof.

Cause: the "Sort by:" label (`label.v2-field` in `.v2-lg-phonesort`, drawn by `phoneSort()` in `app/v2/league.js`) is as wide as its longest option, and nothing let it shrink. Since #932 (JEG-1081) the Team summary selector's longest option is "DDF Value (projections) rank", so the label and its select ran past a 320 px phone. Page overflow with the fix reverted: 1 px with Inter, 14 px in CI fonts (DejaVu Sans). At 360 and 390 px there was none. The ticket's 10 px was not reproduced in either setup here (probably another font set); the element is the same.

Fix: two rules in `app/v2/v2.css` next to `.v2-lg-phonesort` (`min-width: 0; max-width: 100%` on the label, `min-width: 0` on its select). They apply to the phone sort bar only; Compare and the 44 px controls are untouched.

Test: the 320 px overflow error had been masking a weak guard. With the overflow gone, the "sort selector is dead" mutation in `test_guard_fails_on_broken_builds` was no longer caught, because the 4-team fixture's default order already matches the order the cards check expects. `check_phone` now also asserts the page's `aria-sort` state after the selector changes (`benchF:descending`, `capture:descending`). This adds a check; no assertion was loosened.

### Verified (check named)
- Overflow at 390/360/320 px, before and after the CSS rules, with Inter and with fontconfig rejecting Inter, JetBrains Mono, Carlito and Caladea (sans-serif = DejaVu Sans): scratch script reading `scrollWidth - innerWidth` and the bounding rects of every element past the right edge.
- `tests.test_v2_league_phone_render` (both tests): fails before the fix (1 px Inter, 14 px CI fonts), passes after in both font setups. Playwright 1.49.1 in a venv outside the repo, `RENDER_TESTS_REQUIRED=1`.
- Screenshot of the sort bar at 320 px in CI fonts after the fix: the select sits inside the card.

### Claimed, not confirmed
- That #932 introduced it: inferred from the diff (it added the longest option label); I did not rebuild the pre-#932 tree to measure it.
- `tests.test_v2_waterfall_render` fails the 1366x768 Compare fold in this sandbox (bottom 838 px) with and without this change, in both font setups, so it is not from this fix; its cause was not investigated.
