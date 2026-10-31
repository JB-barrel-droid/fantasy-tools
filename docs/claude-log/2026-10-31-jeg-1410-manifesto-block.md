## 2026-10-31 - Manifesto block / JEG-1410

Contract: Keep Jeremy’s Manifesto unchanged and add a short draft mapping block below it. No value or navigation change.

### Verified (check named)
- `python3 -m unittest tests.test_jeg1410_manifesto_copy`: fails on untouched origin/main f58091a3 (block missing), passes after. SHA-256 pins the original article bytes including markup, punctuation and whitespace.
- Playwright CLI with installed local Chrome, 390 × 844: page visible, block follows article, original 12 article headings, horizontal overflow 0. Screenshot `output/playwright/jeg-1410-manifesto-390.png`, visually inspected.
- Current-source review: `app/v2/v2.js` defines the value views and Trade targets gap; `finder.js:979` defines Natural fit against both rosters; `waivers.js:109` evaluates roster impact. These support the named screen mappings. The block groups all 12 ideas and explicitly labels the fuller option/weekly/timing/playoff features not built yet.
- Ownership check: open PRs #1225 and #1217 touch shell.html outside this block; no hot file edited. JEG-1394 is In Progress but requests a lock check, rather than claiming ownership of shell.html. Its associated #1240 edits tests only.
- `make validate` initially failed during sync: bundled Chromium absent. Corrected environment uses installed Chrome; outcome pending.

### Claimed, not confirmed
- Jeremy has not approved this draft copy. No production check, merge or deploy performed.
- GitHub REST API returned rate limit errors during PR inspection; PR creation may be blocked.
