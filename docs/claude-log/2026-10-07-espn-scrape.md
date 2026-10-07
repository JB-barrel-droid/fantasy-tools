## 2026-10-07 - ESPN daily scrape: already fixed, GAP-041/GAP-036 were stale

Contract: fix the ESPN daily CI scrape (GAP-041: `ModuleNotFoundError: identity`,
job green, `espn_season_projections` last written 2026-10-01) and make the
workflow fail loudly (GAP-036).

Finding: nothing was broken. JEG-102 (5568618, merged 2026-10-02) fixed the
import and removed the `|| echo` swallow; the register rows were never closed.
No code change in this session; docs only.

### Verified (check named)
- `gh run list -w espn-supabase-sync.yml`: every run since 2026-10-03 is green.
  Logs of 37132323992 (10-03), 37198939588, 37303319281, 37456804171, 37614484002
  (10-07 11:30Z) each show `wrote 496 season rows + 8928 weekly rows (vintage <that day>)`,
  `ESPN acquired 496 rows`, `saved: 496 espn rows -> espn_season_projections`.
  Each day's payload hash differs.
- Supabase (read-only SQL): `espn_season_projections` has 496 rows with
  `espn_snapshot_date` 2026-10-07, `pulled_at` 11:30:19Z, `_written_at` 11:30:20Z,
  one `_run_id`. 387 older rows (snapshot 2026-09-29, week=3, no `_run_id`)
  remain; `import_supabase_references.build_espn_snapshot` selects the latest
  snapshot date only, so they are not read.
- `output/comparison-chain-status.json` on main: espn content_vintage 2026-10-07,
  content_week 5, health ok, promoted 1/1.
- Workflow on main already fails closed: scrape and save steps use
  `set -euo pipefail`, no `|| echo`, no skip branch; zero-exit-without-CSV and
  <100 rows are `::error::` exits.
- The new risk: fd370ab (2026-10-07 16:09Z, after today's run) moved the
  identity import to `pipelines/lib/legacy_identity.py`; CI has not run it yet.
  Ran current and pre-migration (fd370ab^) scrapers against live ESPN, outside
  the repo with PYTHONPATH unset: both `wrote 496 season rows`, same hash
  2ccbf3c870ea7bc6b5999a30662d5f4f; `cmp` on the CSVs identical, meta JSON identical.
- Regression guard already exists: `tests/test_espn_ci_workflow.py` (12 tests,
  in `make validate` via test-core). Negative check: swapping in the scraper from
  5568618^ and from fd370ab^ makes
  `test_the_module_imports_in_the_repo_layout_and_finds_a_snapshot` fail with
  `No module named 'identity'` (waiver_wire/ is archived); restored, 12 pass.
  No new test added: it would duplicate this one.
- "ESPN published nothing new" cannot turn the job red spuriously: the scraper's
  hash no-op reads the previous hash from `--meta`, which the step deletes first,
  so CI always writes a CSV. A missing CSV in CI therefore means a real failure.
- `make validate` exit 0 (CHROMIUM_PATH set).

### Claimed, not confirmed
- The first CI run with the fd370ab import (next pg_cron dispatch, 2026-10-08
  11:30Z) will succeed. Basis: identical local output above, `data/inputs/player_identity_map.json`
  and `pipelines/lib/legacy_identity.py` are tracked.
- The "Record monitored check" step (added 0b7170b, 12:34Z today) has not run
  yet; today's run predates it.

### Observations, not acted on
- `save_espn_cbs_references.build_espn_rows` hardcodes `week: 2`; the daily
  upsert rewrites that slot. Label only, not a wrong number (the chain uses the
  snapshot date and reports week 5).
