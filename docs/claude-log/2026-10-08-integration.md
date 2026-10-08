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

### Outage: deploys and chain publishes blocked 10:52–12:00 UTC (integrator error)
- Cause: tests/test_espn_tier_matches_leg.py (merged with fix/engine-tidy, fcf7da6)
  imported playwright unguarded. CI has no Python playwright, so it errored (not
  skipped) inside `make validate`: every pages.yml deploy (fcf7da6 .. 2bb1486) and
  the 11:45 bake chain run failed; the live site stayed on a1ff559. My local
  validations passed because playwright is installed locally.
- Fix 4fe8a6c: guarded the import in that test and four others with the same
  pattern. Verified with a CI simulation: `PYTHONPATH=<shim making playwright
  unimportable> make validate` -> rc 0; normal local validate rc 0. Next deploy
  (ff92591) green; manual bake chain published (espn 2026-10-08).
- Process change: every merge now runs both validations before push
  (scratchpad gate.sh); the agent brief requires the same. The tests-hygiene
  lane is installing a browser in CI so gate render tests run instead of skip.
- Also: my background merge command would have pushed after a red validate;
  I stopped it before the push. Merge commands now push only when the gate exits 0.

### Database migrations applied 2026-10-08
- By the integrator: security_lockdown_20261008 (verified: 0 public tables without
  RLS, 0 anon/authenticated write grants; owner reads intact),
  monitoring_6h_and_posture_20261008 (monitoring_security_posture() ok=true,
  11 accepted api.* definer views), retire_player_context_20261008 (guard: the
  three tables were empty), archive_fp_kdst_20261008 (66-row table + view moved
  to schema archive; not deleted).
- By the migrations agent (verified per its report): fc_week4_value_repair
  (591 rows repaired, hash of (id,value) matched the file; 1,773 out-of-scope rows
  deleted), producers_schedule_tidy (drift + weekly-dashboard jobs removed,
  player-trace daily 12:47), players_merge_audric_estime (1475 merged into 4642,
  18 stats rows moved), live_page_synthetic_schedule (daily 12:15 UTC).
- Not applied yet: cbs_bakes_source_urls_20261008 (fix/weeks-tidy) — breaks
  main's CBS saver; applied together with that merge (GAP-MIGRATION-CBS-BAKES-ORDER).
- Advisor residuals (accepted): 10–11 api.* definer views (read-only front-end
  surface), pg_net in public (moving it breaks dispatch history), INFO
  rls_enabled_no_policy on service-role-only tables.
