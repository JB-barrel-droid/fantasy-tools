## 2026-10-28 - Week transition D: stale flag after Thursday 12:00 CT (JEG-1180)

Contract: report each source's served week and a stale state (still on week N
after Thursday 12:00 CT of week N+1, Jeremy 2026-10-27 on JEG-1176) in the
chain status and the health checks, judged per source on the one New York
clock; stale is a warning and never fails the chain. Plus a runbook. The
Tuesday/Wednesday health-check comment on JEG-1176 is not part of this PR.

Changed: `pipelines/week_state.py` (rule: `stale_after`, `source_week_status`,
`annotate_source_weeks`), `pipelines/rebuild_comparison_chain.py` (status
fields `source_weeks.<s>.state`, `stale_sources`, `lagging_sources`,
`stale_rule`; warning annotation), `pipelines/check_reference_freshness.py`
(per-source rows from the served week; statuses current / lagging / stale /
unknown replace current / one_week_behind / stale),
`pipelines/sync_dashboard_artifacts.py` (passes the history index),
`scripts/check_weekly_freshness.py` (per-source report, warning only; today is
the New York day), `ops/watchdog/_common.py` + `ingest_common.py` (shared rule;
"not published" results carry `week_state`), runbook
`docs/week-transition-runbook.md`, Makefile wiring.

### Verified (check named)
- `python3 -m unittest tests.test_week_stale`: 18 tests OK. Frozen clocks:
  Wednesday 12:00 CT lagging, Thursday 11:59 CT lagging, 12:00 / 12:01 CT
  stale, DST (Thursday 11:59 / 12:01 CST), shared vectors
  `tests/fixtures/week_stale_vectors.json`.
- Chain still passes when a source is stale: `ChainStatusStaleTest` runs the
  real `execute_chain` over faked stages with CBS left on Week 4 on Friday of
  week 5: success True, outcome green, failed [] and held []; the same run on
  Wednesday (lagging) has identical success/outcome/failed/holds.
- Mutation checks: cutoff hour 12 -> 0 failed 8 tests; adding stale sources to
  `failed` in `write_chain_status` failed 2 chain tests. Both reverted.
- JEG-1163 and JEG-1164 suites pass unchanged
  (`tests.test_check_weekly_freshness` 18 OK, `tests.test_watchdog_common_helpers`
  OK); now wired into `make test-unit`.
- Also OK: test_week_state, test_week_calendar, test_no_real_clock,
  test_reference_freshness, test_article_discovery, every
  test_rebuild_chain_*, test_record_post_rebuild_validation,
  test_trade_chart_ingest_ci, test_import_health, test_build_lag_gate,
  test_validate_shards, test_run_suite, test_doc_staleness,
  test_sync_health_freshest, test_checkpoints_health_freshest.
- `DDF_NOW=2026-10-29T17:01:00Z python3 pipelines/check_reference_freshness.py
  --output <scratch>` on the checked-out fixture read served weeks from the
  history index (basis `history_index`) and listed the week-7 sources stale.

### Claimed, not confirmed
- Not run here (no Chromium): test_ops_dashboard, test_freshness_display_render,
  test_status_warnings (their `make sync` setup needs Playwright; they error the
  same way on main). `make validate` not run locally.
- A first try moved `_common.content_week()` to the New York day; it broke
  `tests.test_week_calendar` (which injects the watchdog clock through
  `today_ct`), so it was reverted, not the test. The watchdog's target week stays
  Central-date based.
- Discovery-overdue (`DISCOVERY_OVERDUE`, from Thursday by date) is unchanged; it
  is a discovery alarm, separate from the stale flag.
- The site's stale badge (JEG-1178) and the JEG-1176 Tuesday/Wednesday health
  comment are other tickets.

## Review fixes (source freshness lane, 2026-10-28 13:45Z)

Independent review on #1022 found a blocker: after Thursday 12:00 CT every
source one week behind got `freshness_ok: false`, which the page shows as
"Not updating" ahead of "Held".

- `freshness_ok` is true again for a source up to one week behind (as on
  main); stale rides in its own `stale` / `week_state` fields. Two weeks
  behind is still `freshness_ok: false`.
- Dropped `summary.judged_at` (a wall-clock field `dist_manifest` does not
  ignore).
- `_with_week_state` is guarded: a failure computing the week state returns
  the quiet skip unchanged instead of failing the ingest.
- Kept the New York date in `check_weekly_freshness.py` (JEG-1177's one
  clock); its Wednesday critical check now starts at midnight New York.

Verified (check named): `python3 -m unittest tests.test_week_stale
tests.test_chain_stuck_alert` (39 OK); `test_one_week_stale_is_not_not_updating`
fails with the old line; the reviewer's replay (current fixture, clock Thu
2026-10-29 12:01 CT) gives all 7 sources `stale: true, freshness_ok: true`.
Claimed, not confirmed: Chromium render tests (run in CI).
