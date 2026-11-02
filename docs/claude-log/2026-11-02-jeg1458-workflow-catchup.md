## 2026-11-02 - JEG-1458 workflow catch-up

Contract: bring PR #1257 up to current main by merge commit, preserve writer
credential checks and the release pause alongside counter attribution, fix the
reported offline test failures, and hand the pushed head to independent review.

### Verified (check named)
- The existing remote head `672b566d` already resolved the nine workflow
  conflicts. Merging main `5381de25a6d6b8356eb799c077d48f5fab9e00dc` added no new
  conflicts. No behavior choice was required.
- A YAML comparison of all nine workflows against that main checks every
  original job/step control and environment reference, and byte equality of
  publication/auth/pause scripts. All passed; the added labels and counter
  uploads coexist with main's guards, including anchored branch-job steps.
- `python3 -m unittest tests.test_supabase_bytes_rollup
  tests.test_rebuild_chain_consolidation_nonblocking`: four failures before the
  repair, all 18 tests pass after it. Mutations now target named step fields
  rather than environment ordering and verify a field was actually changed.
  Both individual publication safeguards remain exercised. The shim inventory
  pin is 33 because main added nine branch jobs sharing the writer steps.
- The main-writer-checks workflow's actionlint file list passed with
  `actionlint -shellcheck= -pyflakes=`.
- `make validate` passed reference, sync, guard harness, and the 26-test Python
  spec suite before being stopped during engine tests: other local sessions
  were already running heavy suites. Full validation is left to PR CI to
  respect the sequential-heavy-suite rule. Generated tracked output was
  restored to the merge index; visible untracked build files were preserved
  under `/tmp/jeg1458-generated-20261102`.

### Claimed, not confirmed
- Final-head CI and independent review are recorded on JEG-1458 after push.
  This session performs no review of its own changes.
- Seven full days of production counters and byte/wire totals remain pending
  after an authorized PR merge. No production collection was started here.
