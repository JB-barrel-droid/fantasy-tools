# Archive

Old concepts that do not connect to the v3 Trade Dashboard front-end are kept
here rather than deleted so git history is not destroyed.

## How to restore

```bash
git mv archive/<date>/<path> <original path>
```

Then re-wire any references (see the "What was changed" note for each item).

## 2026-10-07 — archive-old-concepts

| Path archived | Why |
|---|---|
| `waiver_wire/pipeline/`, `waiver_wire/cron/`, `waiver_wire/README.md`, `waiver_wire/dashboard/index.html` | Waiver-wire product. Published copy not rebuilt since 2026-09-22; no connection to v3 Trade Dashboard. Stub `waiver_wire/dashboard/index.html` left in place for `make sync` (which copies it to `dist/waiver-dashboard/`). |
| `weekly_vegas/pipeline/`, `weekly_vegas/cron/`, `weekly_vegas/README.md`, `weekly_vegas/dashboard/index.html` | Weekly Vegas signals product. Published copy not rebuilt since 2026-09-22; ECR feed retired (JEG-ECR-EXIT). Stub `weekly_vegas/dashboard/index.html` left in place for `make sync`. |
| `lanes/LANES.md`, `lanes/PLAN.md`, `lanes/ROUTING.md`, `lanes/runner.py`, `lanes/chatgpt_tools.py`, `lanes/openrouter_adapter.py`, `lanes/usage_watcher.py`, `lanes/bin/`, `lanes/outbox/`, `lanes/merge_sweep.py`, `lanes/test_usage_watcher.py`, `lanes/validation_allowlist.yaml` | Multi-LLM lane outbox/inbox protocol. Muse jobs are disabled; minimax and ChatGPT lanes are retired. `lanes/protocol.py`, `lanes/plan_status.py`, `lanes/merge_charter.py`, `lanes/plan.json`, `lanes/linear_fixture.json`, `lanes/inbox/`, and `lanes/test_plan_tracker.py` are kept because the Makefile test-unit target runs them (deferred: remove from Makefile after open PRs merge). |
| `JEG-132b-report.md`, `JEG-133-RESULT.md` | Old lane result files, no longer needed. |
| `smoke_test_dir/` | One-line hello.txt smoke placeholder; purpose served. |
| `docs/muse-handoff.md` | Muse/ChatGPT handoff doc describing the retired multi-LLM operating model. |
| `tests/test_weekly_chain_espn_gate.py` | Tests `weekly_vegas/pipeline/bin/weekly_chain.py` which is archived. Not in Makefile test-unit. |
| `tests/test_game_day_espn_gate.py` | Tests `weekly_vegas/pipeline/bin/game_day.py` which is archived. Not in Makefile test-unit. |

## 2026-10-08 — JEG-438 legacy name matchers (GAP-IDENTITY-LEGACY-MATCHERS)

Each kept its own name normalizer (tests/test_one_name_resolver.py LEGACY
list). None is called by the Makefile, a workflow, a test or another module,
so they were archived rather than migrated; a migration could not be checked
against their inputs anyway.

| Path archived | Why |
|---|---|
| `pipelines/rebuild_fp_fixture_section.py` | One-off 2026-09-30 repair of the FantasyPros fixture natives. Hard-codes `data/raw/sources/fantasypros/2026-09-29/snapshot.json` (not in the repo) and writes the fixture directly, outside the chain. |
| `pipelines/rebuild_fp_natives_from_snapshot.py` | Second version of the same one-off repair; same hard-coded snapshot, same direct fixture write. |
| `pipelines/refresh_players_espn_fields.py` | Manual players.json ESPN-field patcher, retired by JEG-402 (bake_players.py is the sole players.json writer; see its docstring). Matched on a private `" ".join(name.lower().split())` key against the ESPN CSV's `player_norm`. |

## What was changed (not just moved)

- `pipelines/lib/legacy_identity.py` created: drop-in copy of the archived
  `waiver_wire/pipeline/bin/identity.py` with the `SNAP` path updated to point
  at `data/inputs/player_identity_map.json`. Preserves the `norm_name`,
  `IdentityMap`, and `SNAP` API.
- `pipelines/pull_espn_projections.py`: updated import from
  `waiver_wire/pipeline/bin/identity` to `pipelines/lib/legacy_identity`.
- `AGENTS.md`: updated to note lanes/ operational infrastructure is archived;
  removed ChatGPT/minimax lane as available option; kept routing table.

## Deferred (requires open PRs to merge first)

- Remove waiver-dashboard and weekly-signals from `pipelines/sync_dashboard_artifacts.py`
  (touched by PR #400). Until then `make sync` copies the stub index.html pages
  to `dist/waiver-dashboard/` and `dist/weekly-signals/`.
- Remove `test_lane_protocol` and `lanes.test_plan_tracker` from `Makefile`
  test-unit, and remove the `plan-status` target (touched by PRs #387, #396,
  #397, #398, #399, #400).
- Archive `weekly-dashboard-load.yml` workflow (touched by PR #398). The job
  NOOPs because no new bundles are published (comment says so).

## Unapplied migrations

None. There are no active pg_cron jobs for the waiver-wire or weekly-signals
products (their cron/ directories contained only runbook markdown files, not
SQL migrations).
