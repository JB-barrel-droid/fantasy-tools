## 2026-10-12 - JEG-481 Find a trade (first slice)

Contract: let the user type in their roster and a rival's and list trades where at least 3 of 4 trade charts say the rival breaks even or wins and DDF Value says the user wins (Jeremy, 2026-10-09 and 2026-10-10 comments on JEG-481). Self-contained module `app/v2/finder.js`, loaded before `modules.js`; no change to `v2.js` or the engine. Card sits on Compare a trade; each row opens in Compare a trade through the existing shared-link hash.

### Verified (check named)
- `tests.test_v2_finder` (node harness): listed only with DDF edge >= 0.05, 3 of 4 charts at net <= 0; a chart missing from a package is dropped from the count (not 0); no-DDF players never searched; default 2-for-2, `maxSize` 3 finds a 3-for-1; 1-for-1 outranks an equal-edge 2-for-2. Six mutants fail (rival test inverted, 2-of-4, missing as 0, edge not required, default size 3, no simplicity weight).
- `tests.test_v2_finder_render` (headless, 1440 and 390, built dist): rosters typed with the card's search; each listed trade's DDF edge equals the engine-row sum, at least 3 charts accept, at most 10 rows, link opens the same players on the two sides, Remove clears the result, no sideways scroll. Two mutants fail (edge sign, link sides).
- `tests.test_v2_modules_render` now includes the Find card (chevron, collapse, expand).

### Claimed, not confirmed
- Ranking weight (10% per extra player) and the 6,000-subset cap are defaults, logged in `docs/math-review-agenda.md`.
- League import, lineup sanity (do not gut your starters) and positional need are not built; ticket stays In Progress.
- Visual polish not reviewed by Jeremy.
