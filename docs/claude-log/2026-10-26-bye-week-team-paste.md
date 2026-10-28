## 2026-10-26 - League paste: a team named "Bye Week ..." merged into the team before it (JEG-1110)

Contract: a 12-team ESPN whole-league paste that contains a team named "Bye Week Bandits" must read 12 teams, each with its own players, while a real ESPN "Bye Week Players" section still parses exactly as before.

Provenance: run by an OpenRouter **deepseek-v4.1-flash** agent (T2/T3). Untrusted until a Claude T1 session re-reads the diff, runs the gate and merges (`AGENTS.md` model tiers).

### Cause (not the one the ticket guessed)

The ticket points at `byeStart` (`app/v2/roster-paste.js:670`, `/^Bye Week Players/i`). That regex is already exact and is on the **matchup** path only. Verified it is not the cause: `P.parse(readFixture("espn-matchup.txt").replace(/Team Zeta/g, "Bye Week Bandits"))` gives `mode "matchup"`, 22/22, teams `["Bye Week Bandits", "My ESPN Team"]` — unchanged by the fix.

The whole-league path (`parseLeague`) never looks at `byeStart`; it cuts the paste at `recordHeaders` and validates each candidate name with `plausibleTeamName`, which rejects anything matching `TEAM_NAME_NOISE_RE`. That regex carried the alternative `bye\b.*`, i.e. **any** candidate line starting "bye" was noise. So `Bye Week Bandits (5-1-0)` produced no head, and its block folded into the team before it. Reproduced before the fix with the render test's own paste layout (`tests/fixtures/league/fixture-20team.json`, first 12 teams):

```
teams found: 11
  "Gridiron Gang" 12
  "Waiver Wolves" 26      <- absorbed Bye Week Bandits' 13 + its own 13
  ...
```

### Fix

`app/v2/roster-paste.js`, `TEAM_NAME_NOISE_RE`: the alternative `bye\b.*` becomes `bye\s+weeks?(?:\s+players)?`, so only the section text ("Bye Week", "Bye Week Players", "Bye Weeks") is noise and a team name starting "Bye Week" is a team. One line, plus a comment naming JEG-1110. This covers all three league sub-paths at once (record beside the name, record on its own line, table-marker header) and the kicker-name filter that shares the regex.

Known limit, left as-is: a team named exactly "Bye Week" is still read as the section text (it is indistinguishable from a "Bye Week" header line). The ticket's rule — "a header followed by a (W-L-T) record line is a team" — was not implemented as a general record-line override; that would also loosen the noise filter for every other alternative ("Defense ...", "Sunday ...") and is a bigger behaviour change than this ticket's Done-when needs.

### Tests added (none edited, none loosened)

- `tests/test_v2_league_paste.js`: a 12-team ESPN paste built from `tests/fixtures/league/fixture-20team.json` (real rosters, the "Bye Week Bandits" name kept — no fixture was edited), in both record layouts; asserts 12 teams, the exact team order, each team's own player count, and that the team before "Bye Week Bandits" is not inflated. Plus a differential case: the same paste with a stray `Bye Week Players` line reads identically to the paste without it, and no team is named "Bye Week Players".
- `tests/test_v2_roster_paste.js`: an ESPN matchup paste with a team renamed to "Bye Week Bandits" keeps both teams, 22/22, 12 + 10, and the real section's 2 `Bye`-slot players.

### Negative test (recorded)

`git stash push -- app/v2/roster-paste.js` then run, then `git stash pop`:

```
  FAIL ESPN league paste with a team named 'Bye Week Bandits': 12 teams, none swallowed (JEG-1110)
       teams found: Gridiron Gang | Waiver Wolves | Dynasty Dads | ... | Blitz Bros
11 !== 12
11 passed, 1 failed          (tests/test_v2_league_paste.js)
41 passed, 0 failed          (tests/test_v2_roster_paste.js)
```

So the new league case fails on the unpatched parser and passes with it. The new roster-paste case passes either way: that path never had the bug (see Cause), and the case is a pin on the single-roster path the ticket asked to check.

### Verified (check named)

- `node tests/test_v2_league_paste.js` — 12 passed, 0 failed (was 10 passed before, both new cases green).
- `node tests/test_v2_roster_paste.js` — 41 passed, 0 failed (was 40; the new case green, no existing assertion touched).
- `node tests/test_v2_extract_players.js` — exit 0 (the other node suite that requires `app/v2/roster-paste.js`).
- `node tests/test_v2_name_format.js` — 29 cases ok; `python -m unittest tests.test_v2_kdef_names` — 3 tests OK (the two Python modules that require the parser).
- The reproduction above (11 teams / "Waiver Wolves" 26 before, 12 teams after) on the fixture-backed paste.

### Claimed, not confirmed

- `make validate` / `make test-unit` were not run; only the node suites named above and their two Python dependants. The parser is not touched by `make test-core`.
- The render tests (`tests.test_v2_league_parsed_render`, the JEG-1095 one) were **not** run: `_built_dist()` needs the synced `build/engine/index.html` + `dist/`, which this worktree does not have, and `make sync` is a publish path this run is not allowed to use. The run ends with `FileNotFoundError: .../build/engine/index.html` before any check executes. The JEG-1095 test still renames the fixture team to "Fumble Bandits" (not edited here).
- No live-site check (parser is client-side; the page change is unpublished).
- Other team names that trip the same broad alternatives (`defen[cs]e.*`, `(mon|tue|...)\.*`) were not tested or changed.

### Files changed

- `app/v2/roster-paste.js` (one regex alternative + comment)
- `tests/test_v2_league_paste.js`, `tests/test_v2_roster_paste.js` (new cases)
- `docs/risk-register.md`: the existing `GAP-LEAGUE-PASTE-BYE-WEEK-TEAM` row corrected (cause was `TEAM_NAME_NOISE_RE`, not `byeStart`) and marked fixed on the draft branch. Overlap risk: the FE lane added the neighbouring rows on 2026-10-25.
- `docs/claude-log/2026-10-26-bye-week-team-paste.md` (this entry)
