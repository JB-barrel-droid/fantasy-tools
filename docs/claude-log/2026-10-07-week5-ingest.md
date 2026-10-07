## 2026-10-07 - Week 5 trade-chart ingest: publisher week, FantasyPros in CI

Contract: get Week 5 USA Today, FantasyPros and CBS charts live. FantasyCalc was
already Week 5; the other three were Week 4.

### Verified (check named)
- Root cause for USA Today/CBS: `ingest_{cbs,usatoday}` asked for
  `_common.nfl_week()` (Thursday flip) = 4 on Wed Oct 7, while USA Today and
  FantasyPros posted Week 5 on Oct 6. `pull_usatoday.discover_url(5)` finds the
  Week 5 article; the 12:07Z run and my 20:4xZ default-week run both ingested Week 4.
- USA Today Week 5 written by CI dispatch with week=5: `INGEST OK week=5
  written=756 review=69 bake_id=usatwk5_2026-10-07_v1` (via the Supabase relay; direct
  fetch 402).
- CBS: `discover_url(5)` returns the Week 4 article; CBS has not posted Week 5.
- Fix: `_common.content_week()` (Tuesday turnover, = `pipelines/nfl_week.current_nfl_week`)
  is the ingests' `week_fn`. A discovered article older than the requested week is
  now a quiet `not_published` skip (nothing pulled or saved); an explicit `--url`
  for the wrong week still raises. Two tests that pinned "stale fallback raises"
  were rewritten to assert the actual rule (no pull, no save); reason: with the
  publisher week a fallback is the normal state until a publisher posts, and
  raising would turn the daily job red. Negative check: with the ops/watchdog
  changes stashed, 3 of 5 `WrapperWeekGateTest` tests fail.
- FantasyPros: the lottery puller that wrote `fantasypros_trade_chart.csv` no
  longer exists, and the repo puller only validated the week. `pull_fantasypros.py`
  now parses the four position tables (1QB `Value`, position from the heading,
  fails closed unless QB/RB/WR/TE each appear), resolves names via
  `save_espn_cbs_references.resolve_name`, writes the CSV + fetch log the saver
  reads, and `--save` calls `save_fantasypros`. On the live Week 5 page: QB 32,
  RB 52, WR 74, TE 20, published 2026-10-06. Curly apostrophes (D’Andre Swift RB 41.6,
  Ja’Marr Chase) failed to resolve; fixed in the resolver call.
  `tests/test_pull_fantasypros_parse.py` (5 tests, in test-unit); with the curly
  fix removed 2 fail.
- FantasyPros added to `trade-chart-ingest.yml` matrix (runs under the daily
  pg_cron dispatch; skips a week already in the DB). Local runs cannot save:
  the local sbclient key is anon and gets 401 on `players`.
- `make validate` exit 0.

### Claimed, not confirmed
- The FantasyPros CI save and the chain picking up USA Today/FantasyPros Week 5:
  see the follow-up entry below once observed.

### Follow-up: chain held the Week 5 candidates on native_drift
- Observed: chain run 37689274819 (21:25Z) imported USA Today 756 rows and
  FantasyPros 531 rows (vintage 2026-10-06) and held both:
  `native_drift:full_12:fail -- 138/239 values moved` (USA Today), `102/171`
  (FantasyPros), "live verification skipped". Drift was the only failing
  check; the rest were coverage warns.
- Cause: the drift rule could only be cleared by FantasyCalc's live-API check.
  The vintage-aware rule (FIX-008 in the risk register) exists only on the
  archived `fantasy-tools-clean` branch, not on main.
- Fix: `review_comparison_candidate.newer_vintage()`: when the candidate is a
  newer publication (higher designated week, or a later content date at the same
  week), drift above 5% is a `warn` naming both vintages. Same-vintage and
  older-candidate drift still fails. Tests in `tests/test_review_candidate.py`;
  the two newer-vintage tests fail on the old reviewer, and the same-vintage
  and older-candidate tests pass on both.
- `make validate` exit 0.
