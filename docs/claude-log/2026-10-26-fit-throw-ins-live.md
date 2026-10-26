## 2026-10-26 - JEG-1108: throw-ins live in the finder search

Contract: Jeremy accepted the rule as is (Natural 67% on the real page, 2026-10-26; no threshold changed). Wire balanceCounts into the finder search so a package with unequal player counts gets the receiving-more team's least valuable rostered player as a listed throw-in.

### Change
- app/v2/finder.js findTrades: one throw-in per missing player (a 1-for-3 gets two), for each package that passes the edge and chart gates with unequal counts, call balanceCounts (rosters and lineup shape from `opts.sanity`, else the search rosters), judge the balanced package again (the throw-in is a real cost), then apply the lineup boxes. The trade carries `addedThrowIns [{side, row}]`. Throw-ins must be priced on DDF Value and every compared chart. A starter as the throw-in keeps the old behavior: nothing added, trade marked `unbalanced`. A balanced variant that equals a package the search also reached directly is one trade, with the throw-in listed (collapse by player ids).
- balanceCounts: their side prices the throw-in on the chart average only when their rows carry it, else on DDF Value (before, no chart average meant no eligible player).
- Finder card note: "Includes <player> (<value>) as a throw-in, so both teams trade the same number of players."

### Tests
- tests/test_v2_finder_balance.py: new throw-in section. Fails if any listed trade has unequal counts, if the 1-for-2 package has no throw-in (M2) listed, if the same package is listed twice, if the throw-in is left out of the edge (12 - 10.3 = 1.7, not 2), and if a starter throw-in is added instead of marking the trade unbalanced. New mutant "throw-ins not wired into the search" (the balanceCounts call replaced) is caught.

- tests/test_v2_finder_fit_render.py: the swapped-roster precondition required both a natural and a force group on the current data. With throw-ins the search now lists natural and market supported groups there and no force group (the 10-for-13 thin ESPN roster keeps its starter-throw-in trades, marked unbalanced, and the rest pass the gates). The precondition's purpose is that the tier-order check has two different tiers to order, so it now requires at least two different fits. The guard-mutant test (which breaks the build and requires the check to fail) still passes. The assertion was wrong about the data, not the code: `tier order` and `edge order` checks are untouched.
- Merge of origin/fe/JEG-1093-finder (main's JEG-1081 "Projections agree" column): kept as an informational cell, row field (`projEdge`, `projAgrees`) and sort column; none of it feeds the fit label (the label still ignores projections, per Jeremy's decision). Opportunities tiers stay natural / market / force.

### Distribution (synthetic reference league, fit_diagnostic.cjs, 189 opportunities)
Natural 55 -> 61 (32.3%), Market supported 97 -> 86 (45.5%), Force 37 -> 42 (22.2%). Counts shift because unequal packages are now balanced rather than judged as they came. No threshold changed.
