## 2026-10-23 - JEG-979: fc_grain_check cycle walk never ended (laptop-2)

Found while root-causing JEG-978 (red `preview` checks on PRs #859, #866, #868).

### Root cause

PR #859 (JEG-920) changed `fc_grain_check` in `pipelines/fidelity_pulse.py` to
walk the stored-to-nearest-live map looking for cycles. The loop stopped only
on `cur == start` or `cur in visited`, and `visited` was filled after the loop.
A chain ending on a column nearest itself (stored std -> live half, half ->
half: the JEG-807 one-list-drift case) appended `half` forever.

- Locally, `python -m unittest tests.test_fidelity_pulse` hung in
  `test_one_list_drifting_alone_is_not_a_column_swap` at 11.7 GB after 4 min.
- In CI, the informational `make test-unit` step died inside
  `test_fidelity_pulse` with "runner has received a shutdown signal" or "runner
  lost communication" (runs 40014037799, 39994927317, 40010847396,
  40008330849). The lost runner failed the whole `preview` job, and
  `continue-on-error` cannot catch that.

The same loop also missed a cycle that excludes the start (a -> b -> c -> b):
b and c were marked visited without being flagged.

### Fix

Stop on any column already on the chain, then flag the closed portion
(`chain[chain.index(cur):]`) when it has two or more columns.

### Verified (named checks)
- `tests.test_fidelity_pulse.FcGrainCheckWalk` (new, 2 tests): pass with the
  fix. Against origin/main's loop, both fail at their 10 s bound ("did not
  return within 10.0s") instead of hanging.
- `python -m unittest tests.test_fc_grain_check tests.test_fidelity_pulse`:
  63 tests OK in about 1 s (previously did not finish).

### Assumed, not verified
- `make validate` was not run locally (Windows); the PR's preview CI runs it.
- Live pulse: no scheduled run has happened since #859 merged (last success
  18:40 UTC), so the live hang is inferred from the code path, not observed.
