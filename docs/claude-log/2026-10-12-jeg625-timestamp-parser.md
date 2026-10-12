## 2026-10-12 - JEG-625 tolerant timestamp parser

Contract: `tests/test_razzball_one_save.py::test_latest_save_rows` failed under
system Python 3.9 because `datetime.fromisoformat` rejects 1-digit fractional
seconds (and a trailing `Z`) before 3.11. Jeremy decided (2026-10-12) to make
the parser tolerant so 3.9 and 3.11+ agree.

Change: `pipelines/lib/timestamps.py::parse_iso_timestamp` (trailing `Z` to
`+00:00`, fraction padded or truncated to 6 digits, then `fromisoformat`; a
non-ISO string still raises ValueError, a non-string raises TypeError). 19
production files, 24 call sites now use it (every time-bearing
`datetime.fromisoformat` in pipelines/). Left alone: three date-only calls
(`load_value_check.py`, `fidelity_pulse.py` `s[:10]`, `fidelity_sources/razzball.py`)
that parse `YYYY-MM-DD` and are unaffected by fractions.

### Verified (check named)
- Reproduced: `python3 -m pytest tests/test_razzball_one_save.py` on 3.9.6 gave
  1 failed (test_latest_save_rows) before the change, 0 failed after.
- `python3 -m unittest tests.test_timestamps` passes on 3.9.6 and on the 3.12.12
  venv (8 tests: 1-digit and other fraction lengths, Z, naive/offset, inputs
  old Pythons already accept compare equal to raw `fromisoformat`, invalid
  strings raise, non-string raises).
- Negative test of the helper: dropping the pad/truncate line made 4 tests
  error. Negative test of the call-site guard
  (`NoRawDatetimeFromisoformat`): reverting `latest_save.py` to raw
  `fromisoformat` made it report `pipelines/lib/latest_save.py:28` and made
  `test_razzball_one_save` fail again on 3.9.
- `make validate` exit 0 with the 3.12.12 venv first on PATH.

### Claimed, not confirmed
- Only the affected tests were run under 3.9; the rest of the suite was not run
  on 3.9 and may have other 3.9 gaps.
- Behavior for unusual-but-valid shapes 3.11 accepts and 3.9 does not (for
  example `+0000` offsets, comma fractions) is unchanged and not normalized.
