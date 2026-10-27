## 2026-10-27 - watchdog helper tests (JEG-1164)

Contract: add hermetic unit tests for the ops/watchdog/_common.py file-age
helpers (age_days, is_today) and run-log helpers (todays_run_lines,
run_failed_time). Tests only: a new file, no production code touched. Written
by an OpenRouter deepseek/deepseek-v4.1-flash run; untrusted until a Claude
review.

### Verified (check named)
- `python -m unittest tests.test_watchdog_common_helpers -v`: 16 tests, OK.
  Covers age_days/is_today with fixed os.utime epoch mtimes and explicit aware
  `now` (ZoneInfo America/Chicago), including the CT date boundary (11:30 PM
  CT on the 20th vs 12:30 AM CT on the 21st -> is_today False); and
  todays_run_lines / run_failed_time with an explicit fixed `day`, missing-file
  and other-day-line cases, and other-day lines excluded from the returned
  list.
- Mutation check: made run_failed_time keep the first FAILED instead of the
  latest (added `and latest is None` to its guard); test_latest_failed_stamp_of_day
  then failed (got 06:05, expected 18:15). Reverted with
  `git checkout -- ops/watchdog/_common.py`; suite returned to OK. No mutation
  was committed.
- No real clock read: every call passes an explicit `now` or `day`.

### Claimed, not confirmed
- That these are the only behaviours worth pinning in _common.py; a Claude
  reviewer may want extra edge cases (e.g. unknown-only lines, malformed
  stamps).
