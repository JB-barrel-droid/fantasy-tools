## 2026-10-28 - JEG-1155 content week max: one definition (split from JEG-1128 item 2)

Contract: make the content week's upper bound come from one definition shared by
`curve-widget.js` and `product-data.js`. The widget took weeks 1 to 17. The
calendar (`product-data.js` `CONTENT_WEEK_MAX = 18`, a port of
`pipelines/nfl_week.py` `REGULAR_SEASON_WEEKS`) runs to 18. So in NFL week 18 the
page's own content week was one the reader could not set.

Change: `product-data.js` exports `CONTENT_WEEK_MAX`. The widget's
`setLineupSettings` reads `window.TradeValueProductData.CONTENT_WEEK_MAX` (the
page loads product-data.js first), and its error text uses that same number. If
product-data.js has not loaded, it throws a plain Error and does not fall back to
a number of its own. No value math, `dist/` or `value-model.js` change.

Why 18, not 17: `nfl_week.py` is the source of truth. The 17 came in with
JEG-527 (#598, 2026-10-15), together with the v2 "Data through week" stepper's
`1, 17`. Neither the commit, its log
(`docs/claude-log/2026-10-15-jeg527-season-week-inputs.md`) nor
`docs/methodology.md` ES-12 gives a reason for capping the content week at 17.
ES-12 drops week 18 from every *window*, which is a separate thing from the
content week. A content week of 17 or 18 both leave the default window empty
(`lineupWindow` gives [18, 17] or [19, 17], horizon 0), so allowing 18 changes no
number.

### Verified (check named)
- `python3 -m unittest tests.test_source_freshness`: 30 tests OK on the branch,
  including the new `ContentWeekBoundTest` (4 tests, FRESH-WEEKMAX). It runs the
  real `TradeValueCurveControls.setContentWeek` in Node with an inert DOM stub
  (new `content_week_bound` command in `tests/source_freshness_harness.js`).
- On a worktree of origin/main 046d4cf5, with the branch's test and harness
  copied in, all 4 new tests fail. Week 18 is rejected with
  "Content week must be a week from 1 to 17", and `CONTENT_WEEK_MAX` is not
  exported.
- The negative test moves `CONTENT_WEEK_MAX` to 20 in product-data.js only. The
  widget then accepts 20 and rejects 21 with "from 1 to 20", which proves it
  reads the shared constant.
- `tests.test_no_real_clock`, `tests.test_week_calendar`,
  `tests.test_product_data_wiring`, `tests.test_curve_default_guard` and
  `tests.test_jeg30_health_diagnostics` pass locally.

### Claimed, not confirmed
- The browser render suites, including `test_v2_season_weeks_render` and
  `test_bench_share_readout_matches_reference`, were not run here because this
  machine has no Chromium. Preview CI runs them.
- `app/v2/v2.js` has a third copy of the bound: the "Data through week" stepper
  uses `stepLine(..., 1, 17)`. In week 18 the stepper shows 18 but cannot step
  back up to it. It was left alone because v2.js is a hot file outside this
  ticket. A follow-up could read the bound from the widget.
- `supabase/functions/get-values/index.ts` and `tests/_edge_pipeline_runner.cjs`
  each keep their own `CONTENT_WEEK_MAX = 18`. These already agree at 18 and were
  not touched (the edge function deploys separately).
