## 2026-10-29 - Projection path starts at the publisher's number / JEG-1199

Contract: Continue PR #1060 (idle since 2026-10-28 16:33 UTC) on
`claude/project-thread-mpceu5`: bring it up to date with main, start each
projection's worked trace at what the publisher supplies, and wire the
projection render test into the Makefile. Display only: no value math, no
Supabase, no deploy, no merge.

### Verified (check named)
- `git merge origin/main` into the #1060 head (`19558c9e`): one conflict, in
  `HANDOFF.md` (the Codex draft note at the top of "Resume here"); resolved by
  taking main's `HANDOFF.md`, since that note is superseded by this log.
- Data read on `data/fixtures/current/players.json` (inline script): for 1,041
  ESPN-priced skill scorings, `espn_ppg = espn_ros / games_remaining` except 3
  (Jaydon Blue, all scorings: ROS / 11 where `games_remaining` is 10). The bake
  (`bake_players.py` ~L947) divides a player ESPN lists without a team by the
  whole ROS window, not his pipeline team's games. So the page cannot show the
  divisor honestly from `games_remaining`; the ESPN step shows the total only
  and says in words what it is divided by.
- `rz_ppg` is Razzball's per-game read and the engine's native
  (`curve-widget.js` `PPG_FIELD_OF`); `rz_ros = rz_ppg x games_remaining` for
  every fixture row (same inline script), and is not used by the engine.
- CBS ROS: `pull_cbs_ros_projections.py` L177-210 rescores CBS's non-PPR total
  by receptions and divides by CBS's `gp`; neither the total nor `gp` reaches
  `players.json`, so the CBS step is text only.
- `node --check` on `app/v2/audit-source.js` and
  `app/trade-value-chart/assets/product-data.js`.
- `python3 -m unittest tests.test_render_sweep_shards` OK.
  `tests.test_render_sweep_coverage`: `test_v2_audit_projection_render` no
  longer listed as unwired; 4 failures remain for 4 other modules
  (`test_interactive_trades_release_render`, `test_jeg1263_simplified_site_render`,
  `test_v2_compare_rosters_render`, `test_v2_finder_guardrails_render`), the
  same on the branch before this change.
- Hermetic product-data tests (`test_product_data_wiring`, `test_static_export`,
  `test_source_combo_contract`, `test_retired_extras`, `test_no_real_clock`,
  `test_asset_load_retry`, `test_ddf_composite_value`, `test_week_calendar`):
  78 run, OK (13 skipped).
- `make validate` build step ran; `make -i test-core` ran every test-core
  module: one error, `tests.test_week_history` ...`agree_in_the_transition`,
  `ModuleNotFoundError: No module named 'playwright'` in
  `value_check.run_engine` (this environment has no Playwright); every other
  module passed or skipped. Generated build output was restored, not committed.

### Claimed, not confirmed
- `tests/test_v2_audit_projection_render.py` (extended to pin the first step's
  title and its readouts to `TradeValueProductData.getPlayers()`, and Razzball's
  published per-game to the engine native) was not run: this cloud session has
  no Playwright or Chromium. It needs a Mac run:
  `RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_audit_projection_render`.
- Live verification of Values auditing > single source not done (no deploy).
- Follow-up worth a ticket: bake the ESPN per-game divisor into
  `players.json` so the ESPN step can show "total / games = points per game"
  without the page deriving it.
