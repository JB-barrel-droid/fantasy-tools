## 2026-10-27 - value_three_way compare helpers (JEG-1166)

Contract: add unit tests for the compare helpers in `tools/value_three_way.py` (`diff_maps`, `series_of`, `readout_of`, `compare_readouts`). Tests only; no existing code changed.

Done by an OpenRouter `deepseek/deepseek-v4.1-flash` run — untrusted until a Claude review.

### Verified (check named)
- `python -m unittest tests.test_value_three_way_helpers -v` — 21 tests, OK (run on this branch and after merging `origin/main`).
- Mutation check: changed `if d > tol:` to `if d >= tol:` in `diff_maps`; `test_diff_exactly_tol_is_not_a_mismatch` failed (`1 != 0`); reverted with `git checkout -- tools/value_three_way.py` and the suite passed again. No mutation committed.

### Claimed, not confirmed
- That `import value_three_way` is side-effect free — asserted by the ticket and relied on here; not separately instrumented.
