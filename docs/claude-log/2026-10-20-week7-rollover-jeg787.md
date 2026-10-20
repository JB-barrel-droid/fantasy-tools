## 2026-10-20 - Week 7 rollover test fixes (part of JEG-675, JEG-787)

Contract: fix CI-red tests caused by content_week rolling to 7 while fixture
data is still week 6 (Supabase egress quota blocks week-7 imports).

### Root cause

Three test files read the real clock (directly or via `make sync` updating
`data/history/index.json` to `content_week: 7`), then run the page or pipeline
against week-6 fixture data.  The mismatch causes:

1. **test_week_history (DeltaRecomputeTest, 3 tests):** the page's
   `compositeKeyOlderWeek` marks usatoday/fantasypros as "not yet published for
   week 7", excluding them from `pipelineState.included`.  The `weekPipeline`
   for saved weeks (2-6) then runs without those sources in `included`, so
   `indexedFactor` is null (0 shared DDF players) and `getWeekValues` returns
   "no Full PPR values for Week N at this setting".

2. **test_v2_contract_render (GL-05, GL-09, GL-16, PV-09):** same exclusion
   removes usatoday/fantasypros from DDF blend, breaking freshness ("no source
   says Current"), Compare's ddf_value_charts availability, and Rank-by
   switching.

3. **test_spec_reference_value_pipeline (LiveDump degenerate test):**
   `pipeline_live.py` reads `content_week: 7` from the history index (updated
   by `make sync`), marks charts with served week 6 as "unpublished", and
   combined with the test's projection holds, leaves `included` empty.

### Fix

- **Browser tests** (test_week_history, test_v2_contract_render): pin
  `window.TRADE_VALUE_TODAY` to the fixture's `built_at` date so the page's
  content-week clock matches the data.  Added `_fixture_today()` helper.
  Added a content-week sanity check inside `collect()` that fails if the pin
  doesn't work.

- **Spec reference test:** copy the history dir into a temp directory with
  `content_week` patched to `max(served weeks)` so the pipeline matches the
  fixture.

### Product behavior at week 7 with week-6 data

The live page still shows values and DDF composites.  Weekly charts (usatoday,
fantasypros) are excluded from the default DDF blend and labeled "not yet
published for week 7" -- this is correct first-load behavior for the Tuesday-
rollover window.  The week-history delta feature is broken for those sources
(indexedFactor=null due to `weekPipeline` using `pipelineState.included`
instead of the saved week's own sources): a latent defect, low-severity, only
visible in the delta popover.

### Verified (check named)

- `python -m pytest tests/test_week_history.py::DeltaRecomputeTest` -- 4 pass,
  7 subtests pass (after `make sync` updates index to content_week: 7)
- `python -m pytest tests/test_v2_contract_render.py` -- 6 pass (after sync)
- `python -m pytest tests/test_spec_reference_value_pipeline.py` -- 21 pass
- Content-week sanity check in `collect()` verified: page_week matches
  max(served_weeks) after the pin
- Negative-tested: without the pin, fantasypros/usatoday Week 2 returns
  "no Full PPR values" (confirmed in browser with
  `page.evaluate(getWeekValues)`)

### Claimed, not confirmed

- `make validate` green (running, not yet complete at time of commit)
- CI green on the PR (will be confirmed after push)
- The `weekPipeline` latent defect (using `pipelineState.included` instead of
  the saved week's sources for history queries) is a separate fix not addressed
  here
