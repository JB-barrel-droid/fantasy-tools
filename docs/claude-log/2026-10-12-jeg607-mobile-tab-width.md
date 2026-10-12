## 2026-10-12 - JEG-607 v2 mobile 390px tab width

Contract: reproduce the 390px render failures, find the overflowing element, fix the CSS, not the assertions.

### Root cause
- At 390px the six short-label tabs sit on one nowrap row exactly 358 px wide. Flex items cannot shrink below content, so the row sat at the limit and "How values work" came out 42.9 px wide, under the 43 px hit-area floor. On a wider-font runner (CI) the same row pushes the last tab past the right edge and the page scrolls sideways, which is the tab-off-screen and overflow symptom in the ticket. Locally `scrollWidth` was 390, so the page itself did not overflow on this Mac.

### Fix
- `app/v2/v2.css`, mobile tab rule: side padding 8 px to 6 px (about 12 px of slack in the row) and `min-width: 44px`.

- Panels suite (1440): the Player values table sits in a `fit-content(64%)` grid column; with the wide column selection the table is 848 px against a 823 px cap, so the table wrap scrolled 25 px. Cap raised to 66% (`.v2-values-grid`).

### Verified (check named)
- 12 other render suites (targets, compare, offer, waterfall, contract, states, ddf, expand, manifesto, risers, how, panels minus the above) green; panels green after the 66% cap (`python -m unittest tests.test_v2_panels_render`).
- `python -m unittest tests.test_v2_ux_render tests.test_v2_nav_render`: red before (43x44 hit area), green after.
- Other render suites: see PR description for the result of the full 14-suite run.

### Claimed, not confirmed
- CI font metrics could still be wider than this Mac's; 12 px slack is an estimate, not measured on CI.
