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
  this week (pie_factors_sane: full_12/TE factor None). That case did not work
  with this change; see the follow-up below.

## Follow-up: a held chart that is also lagging (JEG-1175)

The first chain run after #1016 (40612356639, 01:00 UTC) still failed the
same check, plus the new transition tests. CBS was a week behind AND on a red
review hold (pie_factors_sane). A red hold hides a chart from DDF Value
(JEG-569), and the page's week state only counts DDF Value charts, so CBS was
in neither the Week 8 view's sources nor its missing_sources. #1016 only
treated charts named in missing_sources as lagging.

- `lagging_week`: a chart is lagging when it is not in the view's sources and
  serves an older week (missing_sources no longer required).
- `test_the_replay_is_a_transition`: checks served weeks and absence from the
  view's sources instead of missing_sources.
- New sentinel `TestEngineKeepsOrderWithHeldLaggingChart`: the same replay
  with CBS also on a red hold (validationHold, hold_level red), as in the chain.
- A held chart lagging alone (no other chart on its week, so no view for it)
  is recorded as lagging with a stderr warning and not read in the browser;
  its saved Indexed values are still checked by TestSavedValues. That is the
  state on main today (CBS on Week 7, everything else on Week 8).
- Unit case for a held chart on an older week.

Lesson: the PR's CI dist had no hold on CBS, so it could not see this. The
held replay now covers it. Also: `make test-core` locally regenerates dist/
and app/ assets; stage files by name, never `git add -A`.
