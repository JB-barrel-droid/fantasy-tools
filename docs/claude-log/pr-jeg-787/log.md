## 2026-10-22 - JEG-787 align spec reference hold eligibility with engine

- Root cause: pipeline_live.py `eligibility()` treated red holds as ineligible
  (excluded from pipeline), but the engine (curve-widget.js + value-model.js)
  and methodology VP-1 say held sources are eligible + hidden (in pipeline for
  allocation/weights/pie, hidden from DDF blend and Indexed basis).
- Fix: split eligibility from hidden status. New `source_hidden()` function
  determines whether a source is hidden. `value_pipeline.py run_week()` now
  accepts a `hidden` parameter and excludes hidden sources from the DDF Value
  `members` dict, matching value-model.js `isHidden`.
- Also fixed get-values edge function (`sectionHold()`) which had no amber/red
  distinction: amber holds now return `hidden: false`, matching curve-widget.js.
- Updated methodology.md VP-1 to distinguish amber (labelled, not hidden) from
  red (hidden). Updated SPEC_AMBIGUITIES.md SA-5 to RESOLVED.
- Verified: `make validate` green (all tests including v2 render, value-check
  compare, guard harness). New test `test_red_hold_eligible_but_hidden` proves
  red holds are included but hidden from DDF blend. Updated
  `test_amber_hold_stays_eligible_and_visible` proves amber holds are not
  hidden. Updated all-held test confirms all DDF values are null when every
  source is hidden. No chart-path code changed, so 12-combo sweep not required.
