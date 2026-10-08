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

### Later on 2026-10-08 (launch push)
- Merged: fix/launch-qa, fix/value-small, feat/source-resiliency (+36a0e47),
  fix/razzball-refresh (re-baked on main by its agent), feat/week-history
  (rebased by its agent), fix/cbsros-scrape, fix/cbsros-parity,
  feat/launch-front-door. Each combined state: `make validate` exit 0 plus the
  relevant render/chain suites (e.g. 126 chain/history tests, 23 front-door and
  v2 render tests).
- Conflict fix: pipelines/build_v2_page.py (front door vs the front-end
  session's fb0e7f7): kept head_for_v2/root build and added the front-end's
  color-scheme/theme-color meta and movers.js. Verified both dist/index.html and
  dist/v2/index.html carry `color-scheme light dark` and dist/v2/movers.js exists.
- Retired the cbsros full_12 hand pin in tests/test_static_export.py (commit
  1948653): it blocked the CBS ROS 10-08 refresh (20.3 vs 23.5). Negative check:
  nudging Allen's cbsros section value +3.0 fails
  test_suffix_identity live-vs-section parity.
- pg_cron: added `trigger-cbsros-sync-retry` (0 17 * * 3, dispatches only if no
  row for today). CBS ROS scrape dispatched: 367 rows for 2026-10-08.
- Chain with bake_players=true after all merges: green, nothing held;
  players.json espn 2026-10-07, rz 2026-10-07, cbsros 2026-10-08.
- Live: `/`, `/v2/`, `/classic/` 200 with "Trade Value · Data Driven Football";
  unknown path 404 page; root renders v2, fixedPieIndexed true, 507 rows.
