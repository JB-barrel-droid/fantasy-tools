# JEG-569 part 2: held sources stay in pipeline

**Date:** 2026-10-12
**PR:** #530 (squash-merged)
**Ticket:** JEG-569
**Branch:** be/jeg-569-part2

## What changed

When a source has a fidelity hold, it previously was removed from the pipeline
entirely, which renormalised weights and pie for every remaining source, shifting
their Adjusted and VORP values. The fix keeps held sources in the pipeline
(weights, pie, universe) but excludes them from:

- DDF blend (value-model.js `isHidden` guard)
- Indexed basis (value-model.js, same guard)
- `series` arrays returned to display (curve-widget.js, 5 sites filtered)

Python reference (`value_reference.py`) updated with matching `hidden` parameter
in `_ddf()` and `_rows()`.

## Files changed

- `app/trade-value-chart/assets/value-model.js` — hidden source exclusion
- `app/trade-value-chart/assets/curve-widget.js` — pass hidden, filter series
- `pipelines/value_reference.py` — hidden param in _ddf/_rows/run_pipeline
- `pipelines/fidelity_hold.py` — stop clearing combos for held sources
- `tests/test_ddf_composite_value.py` — assert_held_but_included, family-aware

## Verified

- 15 DDF composite value tests: PASS
- 12-combo headless sweep (3 scorings x 4 league sizes): fixedPieIndexed true
- 33 additional tests (view invariants, superflex, scale agreement): PASS
- Bench share readout (16 failures): pre-existing on main, not caused by this PR

## Key design decision

Hidden sources participate in weight/pie allocation so every other source's
Adjusted/VORP values remain stable. They are excluded from DDF blend AND
Indexed basis (both must be consistent for fixedPieIndexed invariant).
