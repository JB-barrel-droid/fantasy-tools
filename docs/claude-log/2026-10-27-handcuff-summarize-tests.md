## 2026-10-27 - handcuff summarize() unit tests (JEG-1167)

Contract: add `tests/test_handcuff_jump_summarize.py`, unit tests for
`tools/handcuff_jump.py::summarize()` on hand-built synthetic rows, without
touching `tools/handcuff_jump.py`, `pipelines/derive_lineup_parameters.py` or
existing tests.

Done by an OpenRouter `deepseek/deepseek-v4.1-flash` run (headless, tests-only
ticket). Untrusted until a Claude review.

### Verified (check named)
- `python -m unittest tests.test_handcuff_jump_summarize -v` -> Ran 14 tests, OK
  (before mutation, after mutation revert, and after merging `origin/main`).
- Pooled means/counts, including that an unpaired row's games still count in
  `rb2_ppg_with_lead` / `rb2_ppg_without_lead` but the row is excluded from
  `paired_backups` (PooledTotalsTest.test_counts / test_pooled_means_include_unpaired_row /
  test_paired_backups_excludes_unpaired_row).
- Strict `>` on both shares: a backup exactly at the line does not count
  (test_strict_starter_line, test_strict_waiver_line).
- `promoted_to_starter_line`, `mean_starter_line`, `mean_waiver_line`,
  `median_jump`, `mean_jump` hand-computed and matched.
- Top-12 threshold both ways: 3 rows in a season -> index `min(11, len-1)` falls
  back to the lowest, all paired rows qualify; 14 rows -> only rb1 >= the 12th
  highest qualify (`top12_paired == 12`), pinning the `>=` boundary
  (test_three_rows_threshold_falls_back_to_lowest, FourteenRowsTest).
- Threshold is season-scoped (SeasonScopedThresholdTest.test_threshold_is_per_season).
- Mutation check: changing `b > r["starter_line"]` to `b >= r["starter_line"]`
  in the `above_start` line makes test_strict_starter_line and
  test_shares_over_all_paired fail (2 failures); `git checkout -- tools/handcuff_jump.py`
  reverted it and the suite went green again.

### Claimed, not confirmed
- The real `analyse()` / `main()` paths and the nflverse inputs are not
  exercised (by design: this ticket is summarize() only). No check that the
  synthetic row shape matches what `analyse()` emits beyond reading the
  `rows.append({...})` literal.
