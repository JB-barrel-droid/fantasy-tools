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

### Browser comparison: origin/main vs branch (headless, clipboard paste events)

Tested at 1366px and 390px. Textarea preserves newlines (confirmed: tagName
is TEXTAREA, .value retains \n on both versions). Results identical at both
viewports:

| Case                  | main  | branch | Notes                          |
|-----------------------|-------|--------|--------------------------------|
| Yahoo matchup         | 16/20 | 16/20  | Identical (awaiting team pick) |
| ESPN team             | 13    | 13     | Identical                      |
| Plain names (>80%)    | 6     | 6      | name-list path in consume()    |
| Plain names (<80%)    | 0     | 5      | NEW: extraction finds them     |
| Tab-separated columns | 0     | 4      | NEW: extraction finds them     |
| Noisy Fantrax page    | 0     | 10     | NEW: extraction finds them     |

No regression: formats that worked on main (Yahoo, ESPN, clean name list)
produce identical results on the branch. The "lost functionality" is that
name lists below the 80% threshold and any non-Yahoo/ESPN source have NEVER
worked -- not before #877, not before #840 (which introduced paste). The
extraction fallback is new functionality, not a restoration.

The 80% threshold was introduced in #877 (9576a69d, JEG-988). Before #877,
paste went directly to readPage() which only ran Yahoo/ESPN parsers. Before
#840 (cd24e9bd, JEG-853), there was no paste feature at all. No git bisect
needed: nothing regressed between #840 and #877.

### Verified (checks named)

- 33 node tests pass (test_v2_extract_players.js): 12 fixtures, edge cases, fuzz, broken-state proofs
- 36 existing roster-paste tests pass (test_v2_roster_paste.js)
- 4 render test files pass under lock (10 tests total):
  test_v2_finder_paste_render (4), test_v2_finder_box_render (2),
  test_v2_finder_kdef_search_render (2), test_v2_finder_collapse_render (2)
- Browser paste comparison: origin/main vs branch at 1366 and 390, clipboard events
- Textarea newline preservation confirmed (tagName TEXTAREA, .value retains \n)
- CI: make sync passed, make validate passed, v2 render test passed

### Claimed (not verified)

- Not tested on the live site (no `make sync` locally)
- Preview build CI render gate still running at time of writing
- All 12 fixtures are synthetic; no real page dumps tested (see "uncovered" below)

### Fixture gaps (real chrome text not covered)

Synthetic fixtures cover the extraction logic but not real site chrome. To add
real samples, ask Jeremy to paste (Ctrl+A, Ctrl+C) from:
1. A Fantrax team page (the table with all columns visible)
2. A Sleeper app roster export or web roster view
3. A CBS Sports roster page
4. A KeepTradeCut or FantasyCalc trade calculator output
5. A Google Sheets column of player names (clipboard from spreadsheet)
6. An iPhone screenshot of a roster run through OCR (e.g. iOS Live Text)
