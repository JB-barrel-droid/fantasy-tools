## 2026-10-08 - CBS ROS weekly scrape failure (fix/cbsros-scrape)

Contract: root-cause the failed 2026-10-07 11:00Z `cbsros-supabase-sync.yml`
run (dispatched by pg_cron `trigger-cbsros-sync-live`), fix it, make the
scrape resilient where cheap, add a test that fails on the broken state.
No Supabase writes, no pg_cron changes, no write dispatch.

Branch pushed. Not merged.

### Answer in one line
A workflow bug, not CBS: the scrape step's step-summary line read
`snapshot['row_count']`, which the puller never writes, so the step died with
`KeyError` after a good 369-row scrape and the save never ran.

### Verified (check named)

- **Failing run 37611096093 (2026-10-07 11:00Z)**, `gh run view --log`: QB 69,
  RB/WR/TE 100 players each, 0 review rows, `Wrote 369 players`, then
  `KeyError: 'row_count'` from the inline `python3 -c` and exit 1. The save step
  was skipped.
- **Origin of the line**: `git log -S row_count` on the workflow. f041206
  (JEG-128, 2026-10-02 16:16 -0500 = 21:16Z) added it. The only successful run
  (37065360913, 21:11Z) predates it, so every dispatch since f041206 fails.
  c7a24fe re-applied the same line after the JEG-285 rewrite.
- **The puller writes** `summary.n_rows` (and `rows`), never `row_count`
  (pipelines/pull_cbs_ros_projections.py, `main`).
- **10-02 failures (37059509615, 37063023888)** were a different cause: the
  saver's post-upsert count check, `holds 367 rows ... expected 363`. The saver
  on main now prunes rows not in the clean set before counting, so that cause
  is already fixed.
- **CBS is not blocking runners**: the 10-07 runner fetched all four pages. A
  local scrape today (`--date 2026-10-08` to the scratchpad) also gave 369
  rows, 0 review. No relay fallback is needed.
- **Supabase (read-only SQL)**: cron.job 13 `trigger-cbsros-sync-live`,
  `0 11 * * 3`, `SELECT public.dispatch_gha_workflow('cbsros-supabase-sync.yml', '{}'::jsonb)`.
- **Fix**: the workflow reads `['summary']['n_rows']`.
- **Resilience**: `fetch` retries network errors, 429 and 5xx up to 3 times
  with backoff. 403 and 404 fail on the first try. A position page that parses
  to 0 rows now fails the scrape instead of publishing the other three.
- **Test**: `tests/test_cbsros_sync_workflow.py` (6 tests, in `make test-unit`,
  next to test_espn_ci_workflow; not in the `validate` deploy gate, which is
  reserved for wrong numbers). It builds a snapshot with the real puller (fetch
  stubbed with synthetic pages) and runs every `python3 -c` reader from the
  workflow's scrape step against it.
  - Negative: with origin/main's workflow it FAILS with `KeyError: 'row_count'`.
  - Negative: with origin/main's puller, the 3 retry tests error and the
    empty-page test fails.
- `CHROMIUM_PATH=... make validate`: exit 0. Build churn reverted with
  `git checkout -- app dist`.

### Claimed, not verified

- The saver will succeed on today's snapshot. I did not run it (no service key
  locally). The saver code path is unchanged from the 10-02 success, and today's
  scrape has 0 parser review rows.
- Watch GAP-DATA-SNAPSHOT-PINS: `("cbsros", "full_12"): 20.8` in
  tests/test_static_export.py is a hand pin. Once the new vintage reaches the
  chain it may turn `make validate` red if Josh Allen's value moves (CBS today
  has him at 25.28 per game standard). I did not compute the rebuilt leg value.

### Proposed (not applied): retry slot

A second Wednesday slot that only dispatches if the morning run saved nothing.
A same-vintage re-run is safe either way (upsert, then prune, then exact count).

```sql
select cron.schedule(
  'trigger-cbsros-sync-retry',
  '0 17 * * 3',
  $$select public.dispatch_gha_workflow('cbsros-supabase-sync.yml', '{}'::jsonb)
    where not exists (
      select 1 from public.cbs_ros_projections
      where cbs_snapshot_date = (now() at time zone 'utc')::date)$$
);
```

### Integrator

After merge: `gh workflow run cbsros-supabase-sync.yml --ref main`, then
confirm `select max(cbs_snapshot_date), count(*) from cbs_ros_projections
where cbs_snapshot_date = current_date` shows today's vintage.
