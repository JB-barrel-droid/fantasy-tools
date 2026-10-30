## 2026-10-29 - Offline ledger: projection inputs to chart DDF Value (JEG-1280, #1146)

Contract: research only. Hold every chart observation fixed, change only projection inputs, and split each chart DDF Value move into the four stages that carry it (lineup, bench, fill_in, position_weight) by Shapley value, with the unattributed residual reported separately. Engine read only, at main 430791c4. Merged as 8f5cc8a3. Added `tools/research/projection-influence-ledger/` (`ledger.py` freeze/run/check, `js_engine.cjs`), frozen fixtures, `docs/research/projection-influence-ledger/` (memo, `ledger.json` with 816 pairs, readout) and `tests/test_projection_influence.py`.

### Verified (check named, as recorded in the PR #1146 commit message)
- Frozen inputs reproduce `Setting.result()` exactly at 12 settings.
- Residual is 0 in all 816 pairs.
- `js_engine.cjs` matches the Python reference to 4.3e-14 on 136 pairs.
- `ledger.py check --jobs 1` reproduces the `--jobs 6` ledger byte for byte.
- `tests/test_projection_influence.py`: 18 tests pass; mutation runs (guard off, fill-in or weights not frozen) fail the guard and residual tests.
- No engine, spec, reference, config, Makefile, workflow, Supabase or published-output change.

### Claimed, not confirmed
- Scope is the default league and lineup only, no week view.
- The approved seven-player waiver-line average (JEG-1244/#1077) was not at that SHA and is not measured.
- This log was written afterwards from the merged commit, not by re-running the ledger.
