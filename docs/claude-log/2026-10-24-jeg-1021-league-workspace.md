## 2026-10-24 - JEG-1021 league workspace: any number of named teams, team summary, trade opportunities

Jeremy, 2026-10-24: "I want the ability to enter teams and save their names in view. As many teams as I want to. So I can review multiple trades with multiple teams at one time. Make sure things are collapsible. This will also make comparing team value doable across a league." Built from the fully decided spec (`jeg-1021-league-workspace/spec.md`, amendments 1 to 3). No value math touched: `curve-widget.js` and `value-model.js` unchanged, `finder.js` search unchanged (one export added: `api.page`).

**What changed**
- `app/v2/workspace.js`: the saved league (one workspace: named teams, rosters, my team, sort and filter choices), versioned localStorage (`ddf.v2.workspaces`), 1 s debounced auto-save with a status for the Saved indicator, corrupt / unknown-version values reported and not overwritten until a change, export / import JSON, copy as text, share link encoding (base 36 keys). It is also the shared "my roster" store the Waivers tab reads: `store.getMyRoster()`, `setMyRoster(entries)`, `subscribe(fn)` (interface in `jeg-1021-league-workspace/store-api.md`).
- `app/v2/table-sort.js`: one stable sort for both tables (blanks last both ways, explicit tie-break chain, natural first direction per column type).
- `app/v2/team-summary.js`: per team roster / starter / bench value in DDF Value and the Trade chart average (finder.js `lineupValue`, `withChartAverage`), dense ranks in both views, strengths and weaknesses by the median rule (depth at or above expected AND starters at or above the league median; depth only below 3 teams), thin bench, under / overvalued players by the market (gap above 2.0 points), headline.
- `app/v2/opportunities.js`: my team against every other team through `findTrades` / `tradeFit` (finder.js, unchanged), one flat list, cached per pairing (key = both rosters' values + settings), chunked between pairings, at most 20 opponents; the eight columns; overall fit by the section 4.3 truth table; rank = fit tier (natural, value, market-only, force) then fundamentals edge.
- `app/v2/league.js` + CSS: three cards on Find a trade above the two-team finder (kept, unchanged): Your league (add, rename inline, star, up / down, clear, remove with confirm and Undo, paste or search per team, Download / Load / Copy, whole-league load from Sleeper or ESPN), Team summary, Trade opportunities (filters, Hide force fits, Details with the Compare link, 20 rows at a time). Cards on phone, a sort selector, settings changes reprocess everything and keep teams.

**Decisions taken here (to confirm)**
- The existing two-team card stays as it is (25 test files pin its ids); the spec said "replace". Logged for Jeremy.
- `aria-sort` is on the th (valid ARIA), not on the button as the spec's markup showed; the button is the one tab stop.
- Market perception is two sub-columns (chart edge, charts fair), each sortable.
- Ranking inside a tier uses the fundamentals edge (DDF receive minus give), not the finder's size-discounted score.
- Not built: per-opponent row grouping (4.8), arrow-key roving in a player list, league settings inside share links.

**Verified (named checks)**
- `tests/test_v2_league_units.py`: 39 Node checks on the frozen fixtures (2, 4, 20 teams, partial) pass; 22 mutations, each caught by a named check.
- `tests/test_v2_league_render.py` (team list, rename, star, reorder, remove + Undo, paste, Saved, reload, corrupt value, Download / Load; 9 broken builds caught), `test_v2_league_tables_render.py` (summary numbers vs an independent recomputation from engine rows, ranks, sort both ways on every numeric column, rank unchanged by sort, headline stable, filters, Hide force fits, capture equals the engine edge, 1 opponent same table, settings change reprocesses and keeps teams, 20 teams; broken builds caught), `test_v2_league_phone_render.py` (390/360/320 no sideways scroll, cards, 44 px controls, sort selector, contrast light and dark, keyboard sort, one tab stop per header; 6 broken builds caught): all pass.
- `make -o sync validate`: exit 0 on the build before the final polish (null text, rank label, nowrap, tier edge); rerun before the PR (see PR body).
- Fresh-eyes review (separate agent, screenshots of the 12-team league): 12 of 13 rubric items, the settings item not visible in a still; all four task-script questions answerable; verdict DONE.
- Found by looking at screenshots, not by a test: the word "null" printed in the opportunities card, a wrapped rank header, a wrapped number; fixed, with a check and a broken-build proof added.

**Claimed, not checked**
- Share-link open (`#find-trade?workspace=`) and Copy link; whole-league load from Sleeper / ESPN (network); Copy as text; a real screen reader; 3-for-3 and 4-for-4 across 19 opponents (budget in the spec, not timed here); the Waivers tab reading the shared store (no Waivers code exists yet).
