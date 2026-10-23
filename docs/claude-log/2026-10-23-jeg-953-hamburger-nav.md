## 2026-10-23 - JEG-953 mobile phase 2: hamburger navigation

Contract: below the phone breakpoint the top nav collapses to a 44x44 hamburger (Jeremy decision C2, 2026-10-23).
Branch `fe/JEG-953-hamburger-nav`, PR "Mobile phase 2 (part of JEG-927)", not merged. See docs/v2-mobile-plan.md (nav).

### What changed
- `app/v2/shell.html`: `#v2NavToggle` button (aria-expanded, aria-controls=v2Tabs); the existing `<nav id="v2Tabs">` is the menu.
- `app/v2/v2.css`: one delimited block at the end ("JEG-953 hamburger navigation"). Collapsed = under 768 px wide or
  landscape phone (up to 932 x 500, so 844x390 collapses). Menu shows full labels, active item marked with a check
  (plus aria-current), landscape uses two columns, under 420 px the freshness line takes its own row.
- `app/v2/v2.js`: open/close wiring: closes on selection, Escape (focus back to the button), tap outside, hashchange,
  and when leaving the phone layout.
- Tablet (768-1023) and desktop unchanged. Chart code, tables, Writing sub-tabs untouched.

### Tests
- New `tests/test_v2_hamburger_nav_render.py`: 320, 360, 390, 844x390 collapsed/open/select/Escape/outside tap, no
  horizontal overflow, 7 labels, 44 px items; 768 and 1366 keep the tab row. Six simulated broken builds each caught.
- Retired `test_v2_nav_320_render.py` and `test_v2_phone_nav_overflow_render.py` (pinned the short-label tab row on
  phones, which C2 replaces); `test_v2_nav_render.py` no longer pins the 390 one-row layout or its mutation. Not made
  green by loosening: the behaviour they pinned was intentionally removed.
- Verified: hamburger test (2 tests, 6 subtests) and test_v2_nav_render. Screenshots in
  ~/code/fantasy-tools-selfhost-notes/mobile-phase2/.
- Not verified: real-phone behavior (iOS Safari/Android Chrome touch, safe areas, address-bar resize, screen readers).
