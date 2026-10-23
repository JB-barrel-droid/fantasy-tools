## 2026-10-22 - JEG-917 Compare a trade: give/receive/verdict run past the 1366x768 fold

- Problem: `tests.test_v2_waterfall_render::test_waterfall_verdict_layout_example` red on main at 1366x768
  (give/receive/verdict bottom 833.8 vs 768). No horizontal overflow; the columns ran vertically past the fold.
- Cause: the verdict card sets the row height (the two side panels stretch to it). With the JEG-841 headline block
  and JEG-861 deal-read copy, the verdict is ~572px in a 550px-wide column (text wraps to 3 lines, headline "why"
  lines wrap, deal-read text 3 lines, fall note 2 lines); only 506px are available below the page chrome at y=262.
- Fix (`app/v2/v2.css`, `@media (min-width:1280px) and (max-height:800px)` only): verdict column 1.6fr -> 2.2fr
  (`grid-template-columns: minmax(0,1fr) minmax(0,1fr) minmax(420px,2.2fr)`). Verdict 572 -> 502px, bottom 763.9.
  Product copy and the test's layout rule are unchanged.
- Test: `tests/test_v2_waterfall_render.py` guard `no 3-column layout` now removes every 3-column rule (it replaced
  only the first, so it would have stopped catching once a second rule existed); new guard
  `no wide verdict column on short viewports` reverts this fix and must fail the checks.
- Verified: test red before the fix (3 errors, as in the ticket); green after (2 tests, RENDER_TESTS_REQUIRED=1);
  full `test_v2_*render*.py` run result in the PR. Width checks at 1100 and 390 (no horizontal overflow) are in the
  same test and pass.
- Not verified: viewports shorter than 768 (e.g. 1280x720) still run past the fold; not part of the contract.
