## 2026-10-25 - Waivers: paste a whole page (JEG-1104)

Contract: the Waivers tab takes a select-all paste of a roster page or a free-agent page, reusing the team-page parser, and says what it read.

### Verified (check named)
- Before the change the shared parser read 0 players from a free-agent page: `node` run of `DDFRosterPaste.parse` on the ESPN and Yahoo SYNTHETIC fixtures (they have no roster slot labels).
- After: both fixtures read 7 of 7 with no junk unmatched lines, `tests/test_v2_roster_paste.js` (40 passed). Against the old parser the new cases fail (4 FAIL lines).
- Roster pages (Yahoo/ESPN team and matchup real fixtures) still read as `roster`; `tests/test_v2_extract_players.js` and `tests/test_v2_league_paste.js` pass.
- Rendered: the one box fills the right list for Yahoo and ESPN waiver pages and a Yahoo team page, asks for a bare names list, and holds back a roster page pasted into the waiver box: `tests.test_waivers_paste_render` test_paste. Its guard test breaks the row reader, the detection and the wrong-list hold-back, and each fails.
- `tests.test_waivers_render` test_tab and `tests.test_v2_finder_paste_render` still pass.

### Claimed, not confirmed
- The fixtures are SYNTHETIC (built from the existing team-page layouts). Real ESPN, Yahoo and Sleeper free-agent pastes may differ; real ones are requested in the Linear ticket.
- Sleeper free-agent pages go through the general extractor and the text cues; not tested on a real Sleeper paste.
- Decision recorded, not made by Jeremy: one box that detects which list, plus the existing two boxes kept (each now also holds back a wrong-kind page).
