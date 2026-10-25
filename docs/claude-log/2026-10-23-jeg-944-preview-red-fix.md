## 2026-10-23 - PR #849 preview check red: timestamp helper and monitoring manifest (JEG-944)

### What changed
- `pipelines/check_projection_captures.py`: `--now` parsed with `lib.timestamps.parse_iso_timestamp` instead of raw `datetime.fromisoformat` (same result for every input 3.11 accepts; also takes `Z` and 1-digit fractions).
- `projection-capture-sunday.yml`: added the `Record monitored check` step (`if: always()`, check id `projection_capture_sunday`), mirroring espn-weekly-store.yml. The workflow had no recording at all.
- `config/monitoring_coverage.json`: pipeline entry for `projection-capture-sunday.yml` (pg_cron job `projection-capture-sunday`).
- New `supabase/migrations/jeg944_projection_capture_check_20261023.sql`: the `monitoring.check_config` row (weekly, 14400 s grace) the coverage test requires. NOT applied (no database access this session); apply with the cron migration once the workflow is on main.
- Merged origin/main (one conflict, docs/risk-register.md: kept both sides). No rebase, no force push.

### Verified (check named)
- `tests.test_timestamps`, `tests.test_monitoring_coverage` (29), `tests.test_projection_captures` (31): OK.
- `tests.test_v2_targets_render` (2) and `tests.test_v2_waterfall_render` (2) with RENDER_TESTS_REQUIRED=1: OK after the main merge, so those reds came from the stale base, not this PR.
- Negative proofs: restoring raw `fromisoformat` makes test_timestamps fail naming check_projection_captures.py:36; removing the manifest entry makes test_monitoring_coverage fail with "not in config/monitoring_coverage.json".

### Claimed, not verified
- The monitoring row and record step against live Supabase / a real workflow run; full `make validate` was not run (CI will).
