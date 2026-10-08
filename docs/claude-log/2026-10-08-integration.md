## 2026-10-08 - Integrator merges (parallel agent branches)

Merged to main after each branch's own checks, re-validating each combined state:
espn-scrape, small-fixes, freshness-display, v2-market, disagreement-units,
espn-zero-badge, players-bake-auto, v2-targets-2, investigate/qb8,
espn-zero-value, espn-below-waiver, games-remaining, cbsros-8t-qb,
short-chart-waiver, suffix-names, main-table-drift.

### Verified (check named)
- `make validate` exit 0 on every combined merge state before push, plus the
  rendered suites: final run 46/46 (main-table parity, short-chart, suffix,
  cbsros 8t, below-leg zero, ESPN-zero badge, disagreement units, freshness,
  published views and league settings, every v2 render test).
- Hand fixture splices (data/fixtures/current/comparison-sources-data.json),
  both because main's data moved after the branch point:
  - games-remaining: took the branch's `espn` section (main's `espn` had only
    `lineage`/`fetched_at` changes since base; kept main's `fetched_at`).
  - suffix-names: took the branch's `cbsros` section; no overlap with main's
    changed sections (cbs, cbs_adjusted, fantasycalc, fantasypros, usatoday).
  Written in the file's own format (`json.dumps(indent=2)` + newline).
- main-table-drift vs short-chart conflict in comparison-dashboard.js: took
  main-table-drift (the table no longer prices anything; the engine passes the
  short-chart peers itself). Risk-register conflict: kept both sides, then
  removed 5 stale duplicate rows.
- pg_cron: added `rebuild-chain-bake-live` (45 11 * * *, bake_players=true).
  Dispatched the bake by hand once: run 37715085784 green, pushed f262c44 with
  players.json espn_snapshot 2026-10-07.
- After all merges, dispatched rebuild-chain: green, outcome `green`, no holds
  (748d890). Live check: getAllRows 514 rows, fixedPieIndexed true, Waller ESPN
  0 / FantasyCalc 1.5, CBS waiver note present.

### Claimed, not confirmed
- One push (c929e11 merge on top of the front-end's 34367bf) went out before
  re-validating; validate on the combined state passed right after.
