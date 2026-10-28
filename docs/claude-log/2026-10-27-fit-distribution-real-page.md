## 2026-10-27 - Real-page fit label distribution (JEG-1096, session:cma)

Contract: re-measure the league-wide Find a trade fit labels on current main after JEG-1108's fit rewrite, on the real built
page, and leave a named check that does it. No rule or value change.

### Verified (check named)
- New `tools/fit_distribution_page.py` (built dist + Playwright, page clock pinned to the data week) on main 33e138e5,
  build tv-20261027-1736-33e138e5:

  | League | You | Opportunities | Natural | Market supported | Force |
  |---|---|---|---|---|---|
  | 20team | 0 | 34 | 7 (21%) | 0 | 27 (79%) |
  | 20team | 3 | 52 | 13 (25%) | 0 | 39 (75%) |
  | 20team | 7 | 1 | 0 | 0 | 1 |
  | 4team | fixture | 7 | 4 (57%) | 0 | 3 (43%) |

- `node tests/node/fit_diagnostic.cjs` (synthetic engine rows, same 20-team league, team 0): Natural 61 (32.3%),
  Market supported 86 (45.5%), Force 42 (22.2%), 189 opportunities.
- Without the clock pin, the same page today (Tuesday, week flip, chain failing since the morning) shows "No trade chart is
  available this week, so acceptance cannot be judged." and zero rows for every league (`app/v2/league.js:981`).

### Claimed, not confirmed
- Why the real page now gives 34 opportunities / 7 Natural for team 0 where the JEG-1108 log (2026-10-26) measured 89 / 60:
  not bisected. Candidates are the data week and the merges since (#957 bench seats, #962 overrides).
- Jeremy's own leagues were not measured; none are attached to the ticket.
