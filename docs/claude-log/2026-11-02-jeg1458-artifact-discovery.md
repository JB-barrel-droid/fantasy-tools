## 2026-11-02 - JEG-1458 artifact discovery correction

Contract: address PR #1257's open artifact-discovery review thread without
changing workflow behavior, published values, or production data.

### Verified (check named)
- Latest comments, commits and exact-head CI were read before editing; the
  prior timestamp repair is already present on 73fb9bad and was retained.
- Regression test `test_download_includes_recent_artifacts_from_old_runs`
  failed before the fix because discovery queried workflow run creation time.
  Repository artifact discovery now includes recent artifacts from old runs,
  paginates metadata, excludes unrelated/old/expired artifacts and downloads
  by artifact ID. Counter timestamps still filter report membership.
- `RENDER_TESTS_REQUIRED=1 /Users/botcomp/code/fantasy-tools/.venv/bin/python
  -m unittest tests.test_supabase_bytes_rollup tests.test_timestamps`: 17 pass.
- The former encoded-run-query test asserted the flawed run-creation rule;
  replaced it with the old-run artifact regression, preserving API failure
  stop-without-retry coverage. No fixture changes.
- `git diff --check`: passed. Another `make validate` is active, so no
  competing full validate or render suite was started.
- No main integration this turn; ticket last_rebase remains the existing
  normal merge of 3799ff1e. HANDOFF.md is untouched. F1 does not apply to
  offline CI measurement tooling. Scoring modes and value math are unchanged.

### Claimed, not confirmed
- Full CI on the correction head and independent delta review are pending.
  Last independent review receipt: 531764f236089f3b53ac9681bc40c814bf9c4af0.
- Seven measured days remain future ticket work after authorized merge.
