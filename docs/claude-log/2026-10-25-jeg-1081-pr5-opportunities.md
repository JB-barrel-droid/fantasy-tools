## 2026-10-25 - JEG-1081 PR 5: projections agreement in the opportunities table

Contract: the league workspace trade opportunities table gets a "Projections agree" column (spec v2 2f, 4c): a tick when DDF Value (projections) gains you on the package, a cross when it loses you, a dash when level or when a player has no projection. The under/overvalued lists were built in PR 4 (both old market columns stay beside the new disagreement list, accepted).

### Verified (check named)
- `tests.test_v2_league_units` (node harness): projEdge equals received minus given in DDF Value (projections) recomputed from the rows; agreement is true at +0.05, null at 0.049, false at -0.05, null for NaN/null; no projections means null (never 0); one package player without a projection makes the trade null (never a partial sum); both a tick and a cross occur in the fixture; the column sorts tick, cross, blank. Three new mutants (direction flipped, level counts as agreement, missing counted as 0) are caught.
- `tests.test_v2_league_tables_render` (live page): header has the tooltip, every cell carries words for a screen reader and a state-specific tooltip, each cell's mark equals an independent recount from the engine rows by player name, each phone card has its projections line, 10 cells per row. Six new guards (inverted, cell not drawn, column dropped, header without tooltip, no screen-reader words, no card line) are each caught.
- `tests.test_v2_league_phone_render` passes with the team-name sort check.

### Fresh-eyes review (separate subagent) and what changed
- Fixed: header tooltip per spec 4c; state-specific cell tooltips; check that ticks or crosses exist; screen-reader and phone-card assertions; comment said 0.1 where the threshold is 0.05; positioned cell for the screen-reader text.

### Test fixes made while here (both reproduced on clean main, neither caused by this PR)
- `test_v2_league_tables_render` "the 4-team fixture shows no force fit": the table lists 20 rows at a time and force fits rank last; with 30 opportunities (2 force) the check read only the first page. It now expands the list first. Assertion intent unchanged. This was not transient: it recurs whenever the rebuilt data gives more than 20 rows.
- `test_v2_league_phone_render` guard "the sort selector is dead": on the rebuilt data the bench-value order equalled the rank order, so a dead selector passed. A second check sorts the cards by team name and requires the order to differ from the rank order.

### Claimed, not confirmed
- Opportunities "under/overvalued" lists beyond the team summary's were not added (the table has no such lists).
- Playwright browser mismatch on this machine (see risk register); validate was run with CHROMIUM_PATH.
