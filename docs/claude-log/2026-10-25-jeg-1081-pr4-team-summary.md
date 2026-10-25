## 2026-10-25 - JEG-1081 PR 4: team summary tri-view

Contract: the league workspace team summary shows three ranks (DDF Value, DDF Value (projections), Trade chart average), speaks in position allocation language instead of "fundamentals/market", and lists the players where the projections and the adjusted trade charts disagree by more than 2.0 points, labelled "Projections higher" / "Projections lower" (spec v2 2d, 2e; Jeremy 2026-10-25: primary view DDF Value, position-neutral list skipped).

### Verified (check named)
- `tests.test_v2_league_units` (node harness, frozen fixtures untouched; rows get projection values in the test): third rank equals an independent dense rank of the projections lineup; no projections means no third view and no rank (never 0); a team missing one projection gets no view while the others are ranked; the disagreement list matches an independent recount per team (floor 2.0, nothing at 0 or at 1.99, size order); the gap reads `ddf_value_charts` when the row has it; the column sorts on the signed biggest gap; strengths say "allocation above/at or above" and weaknesses "allocation below"; headline "Your team ranks Nth of M on DDF Value, Nth on projections, Nth on market. Position allocation: heavy at X, light at Y." Seven new broken-build mutants (floor, sign, rank source, wording, view built from one player, charts key, unsigned sort) are each caught.
- `tests.test_v2_league_tables_render` (live page, 1440): columns, third rank numeric, projections-vs-charts cell sign matches higher/lower, headline "on DDF Value ... on projections", caption and DDF Value rank wording; three new guards (rank cell empty, list not drawn, labels swapped) caught.

### Fresh-eyes review (separate subagent) and what changed
- Fixed: a team with only some projected players no longer gets a projections view (it would rank low); the headline names the biggest gap in either direction ("above"/"below"); the column sorts on the signed gap; card lines use the new view names; footnote says the gap is against the adjusted trade charts.
- Not done: the spec's "default the disagreement list, market-vs-DDF on a toggle". Both lists stay visible on the table (new column beside the existing two) to keep the pinned table tests; phone cards show all of them.

### Claimed, not confirmed
- test_v2_league_tables_render's opportunities check "4-team fixture shows no force fit" fails on current main without this change (live data refresh since PR 3 validate); not caused by this PR, not fixed here.
- The sync step now launches a browser (values explainer); this machine's Playwright wanted a browser build that is not installed, so validate was run with CHROMIUM_PATH pointing at the installed headless shell.
