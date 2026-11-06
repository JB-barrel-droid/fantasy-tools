## 2026-11-06 - Raw fromisoformat guard failure / JEG-1525

Written by Muse.

Contract: fix the preview-shard (1) CI failure on PR #1325 at its root.
The failing check was `tests.test_timestamps.NoRawDatetimeFromisoformat`:
`pipelines/merge_churn.py` parsed timestamps with a raw
`datetime.fromisoformat(...)` call, which the repo guard (JEG-625) forbids
because raw parsing breaks on 1-digit fractions before Python 3.11.

### Verified (check named)

- `python3 -m unittest tests.test_timestamps tests.test_pipelines_import_standalone`:
  failed before the fix on `pipelines/merge_churn.py:15`; passes after (10 tests, OK).
- `python3 -m unittest tests.test_merge_churn`: OK after the fix.
- The fix routes parsing through `parse_iso_timestamp` from `lib.timestamps`
  (handles `Z` and fractional digits natively, same values for every input the
  old code accepted), with the house sys.path bootstrap so the module imports
  standalone. No assertion changed; no test weakened.

### Claimed, not confirmed

- Live CI on the new head and the delta re-review are coordinator steps after
  this commit is pushed; not performed in this pass.
