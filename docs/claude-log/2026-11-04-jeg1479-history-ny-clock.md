## 2026-11-04 - JEG-1479 week history reads pull times on the New York clock

Contract: unblock Week 9 publication. The chain's week history capture failed
on every run since the Week 8 -> 9 flip, and with no Week 9 history the engine
and Python reference disagreed on all seven sources, which held every source
and left `make validate` red. Fix the capture's FantasyCalc pull-week rule; no value math touched.

### Verified (check named)
- Root cause of the capture failure: run 41952295990 "Capture week history"
  step raised `HistoryError: fantasycalc: week column 8 but pulled in week 9`.
  The row (Supabase `source_trade_values`, bake `fcwk8_2026-11-03t0305_v1`)
  was pulled 2026-11-03 03:05:25Z = Monday Nov 2 22:05 ET, i.e. week 8 on the
  NY clock the content week flips on. `week_of_day` sliced the UTC date.
- Same failure in run 41743526311 (Nov 4 00:00Z, verdict agree) and
  41748067226 (Nov 4 00:36Z, verdict disagree): the capture had been failing
  since the flip; the value check flipped to disagree once CBS Week 9 landed
  (00:35Z) and every chart served week 9 with no week 9 in history.
- The test failure gating publication (`test_python_reference_flag_on_equals_baseline`,
  0 rows priced) is a consequence of the all-source hold, not a separate
  defect: locally, adding `validationHold` to all 7 sections of the committed
  fixture reproduces "0 not greater than 100"; removing it passes.
- First fix (read every pull on the NY clock) failed the branch dispatch
  (run 41958750296): `fantasycalc: week column 8 but pulled in week 7` on bake
  `fcwk8_2026-10-27t0105_v1` (Mon Oct 26 21:05 ET, labelled on the UTC
  calendar). The writer has labelled Monday-night pulls on both clocks, so the
  shipped rule accepts a `week_column_pull` label matching the pull's week on
  either the UTC or the New York calendar; any other label still fails closed.
  Other evidence rules are unchanged.
- `tests/test_week_history_pull_clock.py`: 3 errors without the fix, 5/5 pass
  with it (covers both production rows, ordinary pulls and real mislabels). `tests.test_week_history` WeekSnapshotRule,
  WeekTransitionSentinel and AppendOnly suites pass (19 tests).

### Claimed, not confirmed
- That a fresh Week 9 history alone makes the engine and reference agree.
  Proof is the branch dispatch of rebuild-chain.yml and then the first main
  run after merge (value_check verdict, validate, fixture `as_of`, live `built_at`).
