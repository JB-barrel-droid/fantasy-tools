## 2026-10-08 - Shared series picker, Risers and verdict by DDF Value (JEG-466 / JEG-465 / JEG-467)

Contract: one grouped series picker for Rank by, Risers & fallers and Compare's Player values shown;
Risers opens on DDF Value with the engine's same-input Δ; the Compare verdict reads DDF Value.

### Verified (check named)
- Risers opens on DDF Value; every DDF riser/faller shows the engine's `getPriorWeek("ddf_value")`
  `currentValues` → `values` and their difference (tests.test_v2_risers_render, 1440 and 390).
- The Risers and Rank by pickers put every option in its JEG-474 optgroup in vocabulary order, DDF Value
  first, 44 px tall; a series forced to "no prior week" is disabled with its reason in the label
  (tests.test_v2_risers_render). Broken builds "picker ungrouped" and "Risers default not DDF" fail it.
- With Player values shown switched off DDF Value, the verdict headline still names DDF Value with
  its engine net, the verdict-card waterfall is DDF Value's row, and every table waterfall matches the
  engine (tests.test_v2_waterfall_render, 4 viewports). Broken build "verdict not DDF" fails it.
- DDF Value is the first row of "Difference by source & method" and carries "★ Decides the verdict";
  Values shown opens on DDF Value and is grouped (tests.test_v2_compare_render).
- Side values and totals follow the picker for DDF Value, ESPN, FantasyCalc and an incomplete series
  (tests.test_v2_offer_render).
- `buildMovers` reads "now" from `currentValues` for DDF Value (tests.test_v2_movers, new broken build).
- Manual probe at 1440 and 390 (Playwright screenshots): grouped options, DDF meta line
  "DDF Value · 7 of 7 sources have a prior week", no page errors.

### Claimed, not confirmed
- The "· Wk N" prior-week badge in option labels: the fixture has no stale series, so the test only
  proves no false badge is shown.
- Native `<optgroup>` keyboard and screen-reader behaviour is the browser's; not tested with a reader.
- Earlier week pairs for DDF Value are not offered (BE-3); the served pair only.
