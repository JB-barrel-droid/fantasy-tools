## 2026-10-29 - JEG-1231 opponent inclusion: league page hookup

Contract: wire the JEG-1231 inclusion control into Find a trade (league-wide) with the smallest league.js change, after
#1072. Stacked on the component PR (`claude/JEG-1231-opponent-inclusion`).

Touches: `app/v2/league.js` (the opportunities card only: a control box above the results, `runOpps` searches the
included opponents, results and the single Opponent filter skip left-out teams, `ui:inclusion` drops the old result and
searches again, a JEG-1217 profile change re-runs), `pipelines/build_v2_page.py` (loads the module before league.js and
copies it), new `tests/test_jeg1231_league_inclusion_render.py`. No change to finder.js, opportunities.js, workspace.js,
values, fits, ranking or copy. #1072 edits league.js only in the trade detail and panel fit lines (around 869 and 961);
this PR does not touch those lines.

### Verified (check named)
- `node --check app/v2/league.js`; `python3 -m unittest tests.test_v2_league_units` passes (2 tests, harness and mutations).
- Every scripted edit matched exactly one anchor in league.js and build_v2_page.py (the edit script asserts it).

### Claimed, not confirmed
- `tests/test_jeg1231_league_inclusion_render.py` (offers gone, remaining rows identical, focus kept, star and rosters
  untouched, saved with the league, Clear all message, Select all restores the first result, 390 width) has not run here:
  no Chromium in this container. It runs in the v2 render workflow.
- The card's description still says "Your team against every other team."; the control's count line says how many are
  searched. A copy change there is Jeremy's call.
