## 2026-10-27 - Freshness check unit tests (JEG-1163)

Contract: add unit tests for `scripts/check_weekly_freshness.py` covering the
week expectation rule and every branch of `main()`. Tests only — the script,
`pipelines/nfl_week.py` and all app/value/supabase code are untouched.

Done by an OpenRouter MiniMax-M3.1-Flash run; untrusted until a Claude review.

### Verified (check named)

- `python -m unittest tests.test_check_weekly_freshness -v` — 18 tests, OK.
  `git fetch origin main && git merge --no-edit origin/main` reported
  "Already up to date" (the branch was cut from fresh `origin/main`), and the
  suite was re-run green after that merge.
- Mutation check: changing `scripts/check_weekly_freshness.py`
  `if today.weekday() in (0, 1)` to `in ()` (Mon/Tue tolerance removed) made
  `test_expected_week_accepts_prior_week_on_monday_and_tuesday` and
  `test_monday_published_prior_week_is_accepted` fail; the file was then
  reverted with `git checkout -- scripts/check_weekly_freshness.py` and the
  suite returned to OK.
- The suite never reads the real clock: `main()` is run with the loaded
  module's `dt` patched to a stub whose `datetime.now()` returns a fixed aware
  datetime; all test dates are fixed (2026-10-12 .. 2026-10-18).
- `sbclient` is a stub module inserted into `sys.modules` before the script is
  loaded with `importlib.util.spec_from_file_location`; no network call is
  made and no real `sbclient` is imported.
- Coverage: all-clear exit 0 with `OK:` printed; `has_current=false` breach;
  wrong week and wrong season breaches; `run_created_at` 9 days old breach;
  unparseable `run_created_at` breach; `current_run_count=2` breach;
  `signal_count=0` warning; `bundle_built_at` 9 days old warning;
  `sbclient.get` raising, 0 rows and 2 rows all exit 1; `::error::` and
  `::warning::` annotations printed under `GITHUB_ACTIONS=true` and absent
  without it.
- `git status --short` shows only the new test file and this log entry; no
  existing file was modified.

### Claimed, not confirmed

- The new test module is not wired into any `make` target: `make test-unit`
  lists modules explicitly in the `Makefile`, and this ticket forbids editing
  existing files, so the suite runs only when invoked directly. A follow-up
  ticket should add `python3 -m unittest tests.test_check_weekly_freshness` to
  the `test-unit` recipe.
- Not run here: `make validate` and `make test-unit` (full preview suite); the
  added file touches no build, value or published output.
- Not reviewed by a Claude lead session; T3 output is untrusted until that
  review (AGENTS.md, tier rules).
