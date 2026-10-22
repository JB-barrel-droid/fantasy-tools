## 2026-10-22 - JEG-853 Roster paste parser (phase 1)

- New module `app/v2/roster-paste.js`: deterministic parser for Ctrl+A page
  text from ESPN and Yahoo team/matchup pages. No LLM, no network.
- Exposed as `window.DDFRosterPaste.parse(text, playerIndex)`.
- Verified (34 tests, real scrubbed fixtures): Yahoo team 15/15, Yahoo matchup
  20/20, ESPN team 15/15, ESPN matchup 22/22. Zero false positives.
- Structural parsing prevents false matches from nav chrome (team names
  containing player names like "Hodl Beckham Jr", "Colston's Love(Is)land").
- Yahoo name cleaning: strips glued UI text and injury tags.
- ESPN doubled-name pattern handled.
- Matchup pages detect collapsed bench (benchIncluded=false).
- UI wiring deferred to phase 2 (after JEG-852 tab move).
- PR: #804. Branch: fe/JEG-853.
- Assumed but not verified: bench-expanded Yahoo matchup still parses;
  ESPN structure consistent across league configs.
