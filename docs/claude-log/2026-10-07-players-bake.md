## 2026-10-07 - Daily ESPN anchor bake (fix/players-bake-auto)

Contract: make the ESPN anchor (players.json + data/inputs/espn_projections.csv,
which every other chart indexes to) refresh daily after the ESPN scrape, with
`make validate` deciding whether it reaches main.

### Design
- The bake rides inside rebuild-chain.yml (`bake_players=true` input, pg_cron
  `rebuild-chain-bake-live` 11:45 UTC): download the CSV the latest scrape
  saved -> check it equals Supabase's latest vintage -> bake players.json ->
  the existing chain rebuilds the ESPN legs/section, CBS ROS, fit and adjusted
  sections on it -> the chain step's `make validate` -> the commit step stages
  the CSV + players.json + manifest only on a green chain, with the existing
  rebase-before-push. One commit, one deploy dispatch, no new concurrency.
- Not extending bake-players.yml: a separate bake commit would land a new
  anchor with the ESPN section and every indexed section still on the old one,
  until a chain ran; chaining makes the gate see the whole re-anchored state.
- Not rebuilding the CSV from Supabase: public.espn_season_projections drops
  ESPN's team, the eligible flag and display names, and zeroes ineligible rows.
  An exporter that took team from the players registry disagreed with ESPN on
  traded players (Travis Etienne JAX vs NO, Michael Pittman IND vs PIT), so
  espn-supabase-sync.yml now uploads the exact CSV as an artifact instead.

### Verified (check named)
- Anchor staleness: players.json meta espn_snapshot 2026-10-03; Supabase
  espn_season_projections latest espn_snapshot_date 2026-10-07, 496 rows
  (MCP execute_sql). The table keeps one row per (season, week=2, player_key);
  each daily save overwrites it.
- Root cause: bake_players.py and build_ddf_two_tier_leg.py both read the
  committed data/inputs/espn_projections.csv, last changed in f041562
  (2026-10-03, manual) (`git log -- data/inputs/espn_projections.csv`).
- The chain does not skip on an unchanged fixture: run_espn_source rebuilds
  the 12 ESPN legs and section from the CSV on every run (read
  rebuild_comparison_chain.py), so a new CSV re-anchors on the next chain run.
- `pipelines/check_espn_bake_csv.py`: a local scrape
  (pull_espn_projections.py, 496 rows, vintage 2026-10-07) passes against live
  Supabase; the committed 2026-10-03 CSV is refused ("CSV vintage 2026-10-03 !=
  Supabase latest espn_snapshot_date 2026-10-07").
- tests/test_rebuild_chain_bake.py (13 tests) runs the real restore/sync/
  publish/commit/fail scripts against throwaway git remotes. Negative tests,
  each caught: bake step pushing itself; baked files staged in the red-chain
  branch; baked files not staged on green; restore step removed; bake moved
  after the chain; `make validate` removed from the chain step; bake not gated
  on the input; ESPN artifact upload renamed. Against origin/main's workflows
  static_problems reports "bake_players is not declared" and "bake step
  missing".
- tests/test_rebuild_chain_workflow.py `test_losing_continue_on_error_is_caught`:
  its mutation removed the FIRST `continue-on-error: true`, which is now the
  bake step's, so it mutated the wrong step. Fixed to target the chain step;
  the assertion is unchanged (the test was wrong, not the rule).
- Full local simulation of a bake run (Supabase reads only: the anon client
  plus a players dump via MCP): fresh CSV -> bake (613 players, as_of
  2026-10-07) -> ESPN chain stage (12 legs, section, review passed) -> CBS ROS
  stage -> fit -> adjusted sections -> make validate. Results:
  - tests.test_static_export failed on two data-snapshot pins only: ESPN
    full_12 Allen 26.7 != 29.5 and espn_zeroed 188 != 197.
  - tests.test_two_tier_frontend failed at 8 teams (all scorings): "QB: no
    feasible bench share <= 0.15". Same test OK on clean origin/main. See
    GAP-QB8-FEASIBLE. Every other test-core module and the guard harness passed.
- Pins changed in tests/test_static_export.py (the assertion was wrong under
  the daily-refresh rule, same class as GAP-MAIN-STATIC-PIN): the ESPN 26.7
  pin -> `espn_anchor_problems` (section natives recomputed from the committed
  CSV, one vintage across CSV / players.json / section); the 613 / 188 counts
  -> `universe_problems` (no comparison key missing from players.json, every
  zero has a status). Negative tests: a stale section after a re-bake, and a
  dropped zeroed player, are both caught. With the fresh simulated data
  test_static_export passes.
- `CHROMIUM_PATH=... make validate` exits 0 on the branch (committed data).
- Full unit suite (`unittest discover`): 69 failures / 5 errors on the branch,
  70 / 6 on a clean origin/main worktree; no new failure (diff of FAIL/ERROR
  lines). tests.test_no_failopen_workflows fails on main too
  (source-vintage-check.yml).
- tests.test_monitoring_coverage: OK with the new manifest entry
  (rebuild-chain-bake-live -> check rebuild_chain).

### Claimed, not confirmed
- The workflow has not run in GitHub Actions (no dispatch from the branch:
  its consolidation step writes production Supabase). Unverified there:
  `gh api .../actions/artifacts?name=espn-projections` jq selection, `gh run
  download` with GITHUB_TOKEN, upload-artifact on the scrape.
- The chain's generic sources (USA Today, FantasyCalc, FantasyPros, CBS) were
  not re-run in the simulation (their snapshots need the importer); their
  Allen pins are the 25.0 QB translation max, so they should not move with
  the anchor, but that is reasoned, not run.
- The first scheduled bake after merge will fail at validate on
  GAP-QB8-FEASIBLE and leave main on the 2026-10-03 anchor (by design: fails
  loudly, nothing pushed). The anchor will not refresh until that is resolved.
