## 2026-10-28 - JEG-1175: rank guard checks a lagging chart in its own week

Contract: every Rebuild comparison chain run since 2026-10-26 failed post-rebuild
validation at `tests.test_rank_guard.TestEngineKeepsOrderEverySetting.test_indexed_order_equals_native_order`
("cbs: no Indexed values or native ranks"; usatoday earlier), so week 8 never
published. The lagging charts serve Week 7 while the page's view is Week 8, and
under JEG-1177 (no carry-forward) the view leaves them out. The guard read every
chart in the default view only. Now a chart the view names in `missing_sources`
for an older served week is read in its own week's view (`setWeek`) and must
keep its native order there. A chart missing for any other reason still fails.

The test was wrong, not the engine: the rule it pins (one week for every chart)
was changed by Jeremy on 2026-10-27 (JEG-1176: lagging is normal, no
carry-forward). No assertion was loosened: order is still checked for every
published chart, only in the view it is priced in.

### Verified (check named)
- Chain run 40605906838 (2026-10-28 00:00 UTC) log: the only failure in
  `make test-core` is this test, 14 rows, all `cbs: no Indexed values or native ranks`;
  status file shows cbs served at Week 7, the rest at Week 8.
- `python3 -m unittest tests.test_rank_guard.TestLaggingWeek tests.test_rank_guard.TestCountInversions`
  passes locally (lagging detection, missing-chart failure, older-than-every-view skip).

### Claimed, not confirmed
- `TestEngineKeepsOrderInTransition` (replays CBS and USA Today one week
  behind via `test_week_history.transition_overrides`) passes and would fail on
  the old guard. No Chromium in this session; PR CI runs it in `make validate`.
- The next chain run on main publishes week 8. CBS is also on a review hold
  this week (pie_factors_sane: full_12/TE factor None); a held, lagging chart
  should still read in its Week 7 view, but only the chain run shows it.
