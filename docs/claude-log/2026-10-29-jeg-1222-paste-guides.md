# JEG-1222: fact-check league-paste guides (Claude, 2026-10-29 UTC)

Doc-only. Output: `docs/research/jeg-1222/league-paste-guides.md`. No app,
parser, fixture, runtime copy or design change.

## Verified
- `node tests/test_v2_league_paste.js`: 12 passed, 0 failed on `021c5bf`.
- PR #913 body: whole-league fixtures for ESPN, Yahoo and Sleeper have
  inferred copied-text layouts (ESPN rosters taken from a screenshot).
- PR #804 body and test header: `tests/fixtures/roster_paste/` ESPN and Yahoo
  team/matchup files are real scrubbed Ctrl+A captures (2026-10-22); the ESPN
  capture's menu lists League > Rosters.
- ESPN Fantasy 101 article: League tabs include Rosters, showing every team.
- Yahoo help SLN7137: My Team > Roster. Yahoo's public demo league shows a
  "Starting Rosters" page with every team (read through a page fetch).
- Sleeper help 4238825: web Trades > Trade opens a "full roster view";
  whether it shows every team at once is not stated.
- Help copy and summary wording quoted from `app/v2/league.js`.

## Claimed, not confirmed
- Copied text of ESPN League Rosters, Yahoo Starting Rosters and any Sleeper
  page from a signed-in league: not captured. No sign-in was made.
- Yahoo Starting Rosters menu location.
- A direct page download of the Yahoo demo page was refused by this
  environment's safety check and was not retried another way.

## Next
- Real captures (listed in the doc) to close the blocked rows; Codex owns
  fixtures and parser changes.
- Live copy issues listed in the doc go to JEG-1130 (Codex).
