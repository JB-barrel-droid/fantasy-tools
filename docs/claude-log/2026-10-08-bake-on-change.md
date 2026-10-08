## 2026-10-08 - GAP-BAKE-ON-CHANGE: a projection change publishes the same day (fix/bake-on-change)

Contract: after the change-triggered refresh went live, a CBS ROS re-scrape at
13:53 UTC blocked every publish until the next 11:45 bake (post-rebuild
validate failed `tests.test_cbsros_8t_qb` in every combo). Make the chain bake
players.json from the same snapshots it builds the ESPN / CBS ROS / Razzball
sections from, make the identity explicit (content id, not date), and hold one
mismatched source instead of failing validate for all.

### Verified (check named)
- The 13:53 save was complete. Run 37788007769 log: QB 69, RB 100, WR 100,
  TE 100 parsed (369), `cbsros 2026-10-08: 367 clean rows, 2 review rows`
  (Christopher Brooks, Zonovan Knight no_match), `Verified: cbs_ros_projections
  holds 367 rows`. Supabase (read-only): 367 rows for 2026-10-08; 366 created
  08:48 with pulled_at 13:54 (upserted) + 1 RB created 13:54; by stat shape QB
  69 / rushing 198 / receiving-only 100 (2026-10-02: 66 / 198 / 99).
- The probe's `cbsros WR: no stats table (0 rows)` (run 37787923426) was the
  probe's own page read (probe_failed -> blind ingest `probe_fp=unprobed`);
  the scraper's empty-position fail-close (`pull_cbs_ros_projections.py`:
  `Fail closed: no players parsed for ...`) exists and did not trip because
  every position parsed. The unprobed ack set new_content=false, so the CBS ROS
  ingest did not itself dispatch the chain; the 13:53:55 / 13:54:08 chain runs
  were dispatched by other ingests and picked up the new CBS ROS rows.
- Chain run 37788057253 log: chain green (held=[]), then validate
  `FAIL: test_live_matches_section_on_leg_pool ... full_8 QB 3.931, RB 6.317,
  WR 1.475 ...` -> nothing published.
- `tests/test_bake_on_change.py` 20/20 on the branch. Mutation: making
  `bake_identity_mismatch` and `section_identity_mismatch` return None fails 4
  of its tests and 2 in `tests/test_razzball_refresh.py` (6 failed).
- `tests/test_rebuild_chain_bake.py` 15/15, with new broken-variant tests
  (bake without the decide gate, decide ignoring bake_players, bake before the
  import).
- Related suites (pytest): test_rebuild_chain*, test_cbsros*, test_razzball*,
  test_bake*, test_source_probe*, test_chain_commits_legs - 310 passed after
  fixing one fake leg (test_cbsros_section) that lacked the new id.
- `make sync` then `make validate` exit 0 with CHROMIUM_PATH=Chrome, and exit 0
  with `PYTHONPATH=.../noplaywright` (CI parity).

- Full pytest run (pre-rebase): no branch-only failures beyond fake legs that
  lacked the new id (test_lineage_writers, test_projection_source_kind,
  test_cbsros_section; fixtures given an id). Pre-existing, not mine:
  test_lineage_writers leaves the CBS ROS builder pointed at a deleted temp
  root, so test_cbsros_section fails after it in one pytest process (same on
  origin/main; make validate runs modules separately).

### Changed
- `pipelines/projection_identity.py` (new): content id per input; `decide`
  CLI for the workflow.
- `bake_players.py`: meta `espn_snapshot_id`, `cbsros_snapshot_id`,
  `rz_snapshot_id`.
- Legs (`build_cbsros_ddf_leg.py`, `build_razzball_ddf_leg.py`) record
  `<src>_snapshot_id`; section builders (CBS ROS, Razzball, ESPN from
  `espn_csv_sha256`) write `snapshot_id` and refuse legs from two snapshots.
- `rebuild_comparison_chain.py`: `bake_identity_mismatch` before the legs and
  `section_identity_mismatch` after the section for espn / cbsros / razzball;
  a mismatch is a ChainHalt, isolated like any single-source failure (last
  good section + legs kept). `razzball_bake_mismatch` now uses the id (its
  pinned date test was rewritten: the date rule is the defect).
- `rebuild-chain.yml`: `Decide whether to bake players.json` (ESPN artifact
  best-effort + check_espn_bake_csv; bake=true when forced or any id differs);
  bake reads the imported CBS ROS / Razzball snapshots (was: a second Supabase
  export for CBS ROS, which could differ from the chain's import); an ESPN
  hold after a fresh bake re-bakes on the committed CSV rather than reverting
  players.json (which would orphan the CBS ROS / Razzball sections just built).
- Makefile test-core runs `tests.test_bake_on_change`.

### Claimed, not confirmed
- The workflow path end to end on GitHub (decide -> bake -> chain -> commit)
  is not run here; the scripts are exercised only by the static/behaviour
  tests in test_rebuild_chain_bake. The first chain run after merge will bake
  automatically (players.json has no ids yet), so it is the live check.
- No chart numbers move from this branch by itself (no data committed; new
  `snapshot_id` field only), so no 12-combo sweep was run.
