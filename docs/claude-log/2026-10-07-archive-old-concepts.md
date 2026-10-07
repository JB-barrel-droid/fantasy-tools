## 2026-10-07 - Archive old concepts

Contract: Remove from the active codebase the waiver-wire product, weekly-Vegas
signals product, multi-LLM lanes dispatch protocol, and assorted old lane result
files and docs that have no connection to the v3 Trade Dashboard front-end plan.

### Verified (check named)

- `make sync` passes on the archive-old-concepts branch after all moves — observed
  output: "Dashboard artifacts synced to app/trade-value-chart and dist
  (build tv-20261007-1016-a5e2d8e)".
- `dist/waiver-dashboard/index.html` and `dist/weekly-signals/index.html` are
  updated to stub "retired" pages by the sync step (verified: `head -5 dist/waiver-dashboard/index.html` shows stub HTML, not the old dashboard).
- Pre-existing test failure (`test_known_full_ppr_12_team_source_values` in
  `test_static_export`) is identical on clean origin/main (AssertionError: 25.5 != 25.3) — confirmed by running the same test in ~/code/wt/main. This is not caused by archive changes.
- `test_espn_ci_workflow.ScraperRunsOutsideTheGoalWorkspaceTest.test_the_module_imports_in_the_repo_layout_and_finds_a_snapshot` passes: `pull_espn_projections.py` loads correctly after migration to `pipelines/lib/legacy_identity.py` (import path updated, SNAP now points at `data/inputs/player_identity_map.json` directly).
- `pipelines/lib/legacy_identity.py` created as a drop-in copy of archived `waiver_wire/pipeline/bin/identity.py` with SNAP path corrected to `data/inputs/`. API preserved: `norm_name`, `IdentityMap`, `SNAP`.
- Tests NOT in Makefile test-unit (`test_weekly_chain_espn_gate.py`, `test_game_day_espn_gate.py`) moved to archive — verified not in any Makefile test target by grep.
- `lanes/protocol.py`, `lanes/plan_status.py`, `lanes/merge_charter.py`, `lanes/plan.json`, `lanes/linear_fixture.json`, `lanes/inbox/`, `lanes/test_plan_tracker.py` kept in place — test-unit runs `tests.test_lane_protocol` and `lanes.test_plan_tracker`.
- No pg_cron SQL migrations for waiver-wire or weekly-signals products found. Their `cron/` directories contained only runbook markdown. No unscheduling migration needed.
- Open PRs #387, #396, #397, #398, #399, #400 all touch `Makefile` — no Makefile edits were made. Deferred items listed below.
- `archive/README.md` written with a table of every archived path and reason.
- `AGENTS.md` updated: note that lanes/ operational infrastructure is archived; ChatGPT/minimax lanes listed as retired; lanes/ROUTING.md reference removed.

### Claimed, not confirmed

- `test_espn_ci_workflow` full suite still passes after identity import change — ran single targeted test above; full suite claim requires a `make validate` run with the pre-existing static-export failure excluded. (The static-export failure is pre-existing on main; aside from that the validate run proceeded through all tests before reaching test_static_export with OKs.)
- The stub `waiver_wire/dashboard/index.html` and `weekly_vegas/dashboard/index.html` pages will render on the live site after next deploy. Not verified against GitHub Pages preview.
- No remaining references to archived `waiver_wire/pipeline/bin/identity.py` from outside `archive/` — searched by grep; claimed but not exhaustively confirmed across all script imports.
- `docs/risk-register.md` rows referencing archived concepts (GAP-005 waiver-wire, etc.) need updating — deferred because risk-register is touched by PRs #396, #397, #398, #399, #400.
