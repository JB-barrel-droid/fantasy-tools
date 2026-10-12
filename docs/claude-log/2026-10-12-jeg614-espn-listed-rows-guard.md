## 2026-10-12 - JEG-614 red test: espn_listed_rows discrimination guard

Contract: reproduce the red `tests/test_espn_listed_rows.py`, find the root cause, fix minimally, keep `make validate` green.

### Root cause
- Product code is correct. `test_engine_gives_every_espn_listed_player_a_row` and the reference test pass; only `test_guard_fails_on_pre_fix_widget` failed (Playwright timeout).
- That guard served the 0dbf4bc7 `curve-widget.js` (read from git) into today's page. The old widget calls `ValueModel.projectionRoles`, which the current `value-model.js` no longer has (JEG-508), so the engine never becomes ready and `wait_for_function` times out instead of the guard reporting missing rows. The guard decayed as the widget and its neighbours moved on. It only runs where the old commit exists in the clone (it skips otherwise).
- Same decay in `tests/test_bench_share_low_pie.py` (`test_sweep_catches_the_pre_fix_widget`, `test_recovery_check_catches_the_pre_fix_widget`, aefb8f7): same timeout, found because `make validate` stops at the first red target.

### Fix
- espn_listed_rows: the guard now mutates the CURRENT widget, removing the ESPN-zero rule (`values.set(playerKey, 0)` for `espnProjectsZero` players) so such a player has no ESPN native and no row, and asserts all 12 combos then report problems. It fails loudly if the snippet moves.
- bench_share_low_pie: the two pre-fix tests are removed. The anchor they targeted no longer exists; their discrimination is covered by the existing mutation tests (slider not re-pricing, sticky guardsPassed) and `tools/guard_harness.mjs --simulate espn-anchor`. Assertions removed because the harness could not run, not to hide a product failure.

### Verified (check named)
- `pytest tests/test_espn_listed_rows.py` red before (1 failed, 2 passed), green after (3 passed).
- Negative test: the new guard passes only because the mutated widget yields problems in all 12 combos; the unmutated widget passes `test_engine_gives_every_espn_listed_player_a_row`.
- Browser console on the old widget: `TypeError: ValueModel.projectionRoles is not a function`.
- `pytest tests/test_bench_share_low_pie.py`: 4 passed.
- `make validate` exit 0 with the venv (py3.12) first on PATH.

### Claimed, not confirmed
- `make validate` under the system python3 (3.9.6) fails `test_razzball_one_save` (`datetime.fromisoformat` rejects 1-digit fractional seconds before 3.11). Environment, not a repo defect; validate needs py3.11+ on PATH. Not changed.
- Whether CI main was red for the same reason (CI clone depth decides whether the git-based guards skip).
