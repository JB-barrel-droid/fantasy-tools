## 2026-10-21 - JEG-793 Supabase bytes-per-table counter

Contract: steps 1 to 3 of JEG-793. Count Supabase response bytes per
(method, table) in `pipelines/gh_sbclient.py`, print a summary at exit in CI
(or with `SUPABASE_BYTES_LOG=1`) and to `$GITHUB_STEP_SUMMARY`, and write
`docs/supabase-egress-notes.md`. No schedule or read-pattern change.

### Verified (check named)

- `python -m unittest tests.test_gh_sbclient_bytes` passes with the counter and
  both tests error on the pre-change `gh_sbclient.py` (swapped in from
  `git show HEAD:`), so the guard catches the missing counter.
- The test asserts the summary contains no query params, row values or the
  service key, and prints nothing when neither env var is set.
- `make validate` result: see PR.

### Claimed without confirming

- Byte counts equal wire egress (urllib sends no gzip header; not compared to
  the Supabase dashboard).
- The workflow and table inventory in `docs/supabase-egress-notes.md` is read
  from code and the Mac copy of the pg_cron SQL; the cloud project's cron list
  was not inspected. No numbers were measured.
- The step summary and stderr output were exercised only through the unit test,
  not in a live Actions run.
