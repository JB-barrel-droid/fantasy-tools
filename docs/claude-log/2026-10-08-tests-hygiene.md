## 2026-10-08 - tests-hygiene: every test green and gated, or removed with a reason (fix/tests-hygiene)

Note: this branch was rebuilt on 2026-10-08 as one commit on top of origin/main 7a87540. My first squash (db652f1) was cut against a stale base and would have reverted newer work on main, so it was dropped. The branch now carries code, tests, workflows, Makefile and docs only.

Contract: the goal was that no test is left red outside a gate. I inventoried every
module under tests/ (plus lanes.test_plan_tracker and the node harnesses), then either
fixed each red test to check the current contract, deleted or archived it with a reason,
or reported it as a finding. I also did the work under GAP-013, GAP-DATA-SNAPSHOT-PINS,
GAP-APP-ASSETS-LAG and GAP-020, and made render tests fail rather than skip in CI.

### Before / after

"Before" means the module run alone on origin/main dac0ff2 after `make sync`. Run
without a sync, the render tests failed too (see GAP-APP-ASSETS-LAG). "After" means the
branch with every test-unit command run separately, RENDER_TESTS_REQUIRED=1 and
CHROMIUM_PATH set.

| Test | Before | Cause | After |
| --- | --- | --- | --- |
| test_pull_fantasypros | import error | tested the archived weekly_vegas fantasypros loader | loader classes removed; 26 tests for ops/watchdog/pull_fantasypros green; in test-unit |
| test_lane_runner, test_merge_sweep, test_lane_cli | import error / 34 fail | lanes/usage_watcher, merge_sweep, bin/lane archived 2026-10-07 | moved to archive/2026-10-08/tests |
| test_content_vintage_render | 8/8 fail | badge JS removed from the page in 0ca6ab4; freshness now product-data rows (test_freshness_display_render) | archived |
| tests/ddf_live_reprice_pinned.js | fail, ungated | pinned to 2026-09-30/10-01 legs; the live-vs-section parity is test_razzball_refresh / cbsros_live_section_harness (in validate) | archived |
| test_no_failopen_workflows | 1 fail | `\|\| true` in source-vintage-check.yml | workflow captures rc (exit 1 = change, anything else fails the step); test_vintage_trigger now runs the step under bash -e with a stub (exit 1 survives, exit 2 fails), and I confirmed it fails when the rc capture is removed; both in test-unit |
| test_jeg137_card_script_order | 2 fail | the slip/grace cards were deleted from the page (0ca6ab4) | those checks removed; workflow/sync checks kept; in test-unit |
| test_jeg68_starter_markup | 1 fail | n=349 / markup / share snapshot pins | recompute: n = fixture pool, share = starter/total, markup = 0.85/share; I confirmed it fails with a mutated harness (dropped TE, markup x1.01) |
| test_jeg69_direction_check | 2 fail | knife-edge share pin (fixed: data-free predicate test); CBS ROS fails the direction predicate at ppr/8t and std/10t | **still red: real finding** (live chart health panel shows FAIL at those shapes; routed to views-audit) |
| test_kdst_vorp | 1 fail | K/DST | retired by the kdst lane |
| test_razzball_dashboard_render | 1 fail | stub-DOM harness, 12-source pin | rewritten headless on the built page, plus a negative without razzball |
| test_razzball_production_followups | 1 fail | SourceDateTest harness lacked freshnessText | SourceDateTest removed (covered by test_freshness_display_render) |
| test_guard_harness_recorded | 1 fail | JEG-5 recorded numbers re-pinned 3 times in 3 days | recompute in tools/guard_harness.mjs (same pie and shared set as the current state, delta = total - target, miss >= 10x tolerance); negatives: ESPN simulation and --min-miss-tolerances 100 |
| test_trade_chart_pullers | red on main after 10bd086 (now in validate via test-integration) | test required the old fall-back-to-an-older-week CBS discovery, which 10bd086 removed on purpose | asserts DiscoveryFailed instead (never an older week) |
| test_save_espn_cbs_references | red on main after 928477b (in test-integration, so now in validate) | pinned the 8-column conflict grain; CBS is versioned on the 9-column bake grain (migration cbs_bakes_source_urls_20261008.sql) | asserts the 9-column grain |
| test_freshness_display_render | red on main after the CBS Week 5 promotion | negative relied on CBS being a week behind | CBS put on Week 3 in the test's fixture edit |
| test_public_copy_no_vorp | red on main after the weeks-tidy/views-invariants merges (8 literals: `_vorp` suffix checks, "saved vorp_views", "buildVorpRows on the saved projections ...") | copy decision, not mine | **left red: reported** (test-unit only) |
| test_view_invariants (new on main) | | Playwright skips | required/hermetic like the other render tests |
| test_trade_chart_ingest_ci | 1 fail | matrix literal | fixed upstream the same way while I worked (kept main's version) |
| test_adjustment_inputs | import error (0 tests ran) | live asset version ddf-20261007 has no committed versioned copy | resolved per test; 21 tests run on the served asset; **test_live_asset_has_versioned_copy still red: real finding**. rebuild-chain now `git add data/adjustment-inputs`, so it clears on the next chain run |
| test_source_freshness | 1 fail | ROS-exclusion negative relied on ROS legs being a week behind | ROS legs dated to a Week 4 day in the mixed fixture |
| test_razzball_monitor_coverage | 2 fail | vintage/Gibbs pin; index-math "bad" | natives recomputed from the newest legs, and the loader now reads only the newest legs (I confirmed the new tests fail on the old loader); index-math was red because committed legs lagged the sections; green after the chain committed fresh legs (9a6f707) |
| test_consolidated_write_fields | 1 fail | cbsros vintage pin | compared to the section's own vintage |
| test_check_source_fidelity | 1 fail | searched the current NFL week's article; synthetic is Week 4 | week pinned in the test |
| test_bake_today_unboundlocal | 4 errors | stub schedule predates the bye-table check; CSV lacked weeks_covered | stub builds a bye-consistent season; CSV has weeks_covered |
| test_pipeline_cascade | 1 error (in test-integration) | matcher resolves only via the canonical identity table (2026-10-04) | synthetic identity map |
| test_naming_drift | "Ran 0 tests" | helper named `run` shadowed TestCase.run | renamed; 4 tests run |
| test_lineage_* (freshness, vorp_roundtrip, snapshot_guard) | fail / skip | lineage audit | retired by chore/retire-extras (integrator); my edits there were backed out |
| test_below_leg_zero_render | 1 fail | "no floor" mutation needed CBS ROS withholding 8t QBs, which fresh data no longer does | withheld position forced in the display path (rows, floors, harness view); the mutation is caught again |
| test_public_copy_no_vorp | 1 fail (on main after the math-inspector merge) | `publishedViewMap(key, "vorp")` internal key | exact-call exemption, with negatives |
| test_published_views_render | 1 fail (on main after the math-inspector merge) | mutation anchor matched twice | anchor includes the leading newline |
| tests/rendered_gate/freshness-hero.mjs | fail, ungated | monitor thresholds moved 60/120 -> 360/720 min (cd8f794) | cases 400/800 min; in test-unit |
| razzball_pill_harness, source-import-health-table, trade-qa-open-findings (.mjs) | green, ungated | no target ran them | in test-unit (fleet-headline was deleted by retire-extras) |
| test_two_tier_frontend | 7 skips | golden file from another repo; peaks test skipped since 09-30 | golden variants and the skipped test removed (hand vectors cover the same functions; scale agreement retired) |
| test_lineage_snapshot_guard | 1 skip | needed dated data/raw snapshots | removed (and the module is retired) |
| test_live_page_synthetic | 16 fail | | owned and rewritten by the freshness lane; green on main |
| test_status_warnings | red on main after merges | | fixed on main by ops-dashboard-2 |
| 55 other modules | green, in no target | | added to test-unit |

Every render test in validate skipped in CI before this change. See GAP-CI-RENDER-SKIPS.

### Verified (check named)
- `CHROMIUM_PATH=... make validate` exits 0 on the branch with zero "skipped=" lines.
  CI parity: `PYTHONPATH=<noplaywright shim> make validate` exits 0 (10 render skips);
  the same with RENDER_TESTS_REQUIRED=1 exits 2 ("render test cannot run"), which is
  what CI does if the browser install is missing. It now includes test-integration, plus
  test_vorp_translation_js_parity and test_short_chart_waiver in test-core.
- I ran every test-unit command separately (RENDER_TESTS_REQUIRED=1). The only reds
  are the two findings: test_jeg69_direction_check and test_adjustment_inputs
  (versioned copy). test_lineage_snapshot_guard still skips one test; chore/retire-extras deletes that module.
- CI skips: Pages run 37761190813 log shows disagreement_units_render skipped=3,
  main_table_engine_parity skipped=2, launch_front_door skipped=1, week_history
  skipped=5 (Python playwright absent in CI).
- Live chart health FAIL for CBS ROS: headless 12-combo sweep on a make-sync build of
  dac0ff2 gives ppr/8 "fixed-pie direction" 86.8% and "starter markup" 0.979;
  standard/10 direction 86.1%.
- Absent-source handling (integrator request). With the usatoday and usatoday_adjusted
  sections removed from the fixture, test_static_export and test_week_history pass.
  With espn removed, test_static_export fails ("ESPN anchor section is missing") and
  week_history's served_sources() raises. With usatoday present but its QB1 lowered
  by 2.0, test_known_full_ppr_12_team_source_values and the adjusted recompute fail.
- GAP-020: the guard fails when "DDF methodology" is put back in index.html's role text.
- Hermetic browser: with HERMETIC_ARGS, a fonts.googleapis.com request fails in 0.01s
  (ERR_NAME_NOT_RESOLVED). Every Python render test launch and every
  tests/rendered_gate harness except live.mjs uses it.
- Fresh checkout (GAP-APP-ASSETS-LAG): on an unsynced origin/main dac0ff2 worktree,
  16 render modules failed (dist/classic missing, stale assets). With
  `_render_env.ensure_built()` each test builds first.

### Claimed, not confirmed
- Interaction with 4fe8a6c (main, 06:55): render tests that lacked Python
  Playwright errored and blocked deploys, so that commit made them skip. This
  branch reverses it: CI installs Playwright and a missing browser is an error
  again (RENDER_TESTS_REQUIRED=1 is set only by the CI install step, so a
  machine without Playwright still skips). If the CI install step fails, the
  step itself fails and Pages deploys block. Tests added on main since then (test_bench_share_low_pie,
  test_v2_a11y_render) got the same treatment.
- The CI install step (`pip install playwright==1.49.1` and
  `python -m playwright install --with-deps chromium`) has not run in GitHub Actions
  yet. The first Pages run after merge is the check, and some render tests may go red
  there once they really run.
- test_adjustment_inputs and the razzball index-math test should go green on the next
  chain run. Not observed yet.
- Negative proofs for tests whose discrimination predates this session (e.g.
  test_bake_today_unboundlocal's UnboundLocalError path) were not re-run after the
  harness fixes.
