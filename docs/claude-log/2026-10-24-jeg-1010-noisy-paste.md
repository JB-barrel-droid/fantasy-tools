## 2026-10-24 — JEG-1010 Find a trade: paste tolerates noise from any source

PR #881 (branch fe/JEG-1010-noisy-paste). DO NOT MERGE per task instructions.

### Root cause

roster-paste.js only knew Yahoo and ESPN page formats. Any other source
(Fantrax, MFL, CBS, etc.) fell to "unknown" mode, which ran both parsers and
got 0 matches. The `consume()` fallback in finder.js tried line-by-line name
matching but an 80% threshold blocked noisy pages.

### Fix

Source-agnostic n-gram extraction in roster-paste.js: scans each line with
sliding windows of 4/3/2 tokens, matches against the engine's player index with
normalization (suffixes, nicknames, initial forms, reversed names), disambiguates
using position/team hints on the same line. Defence and kicker lines handled
specially. Extraction is the fallback when format-specific parsers find 0 matches.

finder.js: new extraction UI (placeExtracted) shows "Found N players, ignored M
lines" with ignored-lines disclosure and search-to-add buttons.

### Bugfix found during testing

The firstWords quick-rejection gate treated `normName()` output as a single key,
but hyphenated names like "Amon-Ra" normalize to multi-word "amon ra". This caused
"St. Brown, Amon-Ra" (reversed Last-First format) to be silently skipped. Fixed
by checking each word of the normalized form against the firstWords index.

### Verified (checks named)

- 33 node tests pass (test_v2_extract_players.js): 12 fixtures, edge cases, fuzz, broken-state proofs
- 36 existing roster-paste tests pass (test_v2_roster_paste.js)
- 4 Playwright render tests pass (test_v2_finder_paste_render.py) under render lock
- Yahoo/ESPN parsers unaffected (dedicated tests + render test verification)

### Claimed (not verified)

- Not tested on the live site (no `make sync`)
- GitHub Actions CI not awaited (per task: "DO NOT MERGE")
- No headless browser reproduction of the original bug against the built dist/ (node-level reproduction only)
