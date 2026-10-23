## 2026-10-23 - "DDF Value: charts only" ignores the DDF blend selection (JEG-930)

Decision (Jeremy, 2026-10-23, on JEG-930): the charts-only variant ignores the Customize > DDF blend selection (always the
open trade charts, never blank); the unreachable reason "DDF Projections say X while DDF Value calls it Y" is deleted
(DDF Value now equals DDF Projections). Branch `fe/JEG-930-charts-only-variant`, from origin/main 78a0d2f0.

### What changed
- `value-model.js`, `pipelines/value_reference.py`, `pipelines/spec_reference/value_pipeline.py`: the charts family is not
  filtered by the reader's selection (JS and both Python references, so they stay equal).
- `curve-widget.js` `versionInputs`: charts-only does not filter by `compositeInputs`.
- `v2.js` Customize: the charts-only row counts the engine's chart sources, not the blend draft, so it no longer warns
  "No sources on in the DDF blend".
- `trade.js`: the "projections disagree / say X while DDF Value calls it Y" reason and its helper `sideWords` are deleted.
  The Unclear branch now only says "agree" when the sides match and says nothing wrong otherwise.

### Tests re-pinned (no assertion loosened)
- `test_v2_customize_cleanup_render.py` D3: the old D3 ("a version with no source on says so") was reachable only through
  this bug (engine refuses an empty selection and locks the last usable input; an all-held fixture makes the row
  "Not available", so the old note and cell reason cannot show). D3 now pins the bug itself: after a real blend edit,
  charts-only keeps its values (same count as before), the engine lists its sources, the dialog row has no blend warning.
  Guard proven by three simulated broken builds (each caught): curve-widget.js filtering by selection, value-model.js
  filtering by selection, v2.js row counting the draft. The harness gained an `assets=` option to serve a broken engine file.
- `test_v2_plain_copy_render.py` "projections disagree back": the deleted reason can no longer be reached, so the mutation
  now targets the remaining Unclear "DDF Projections agree" line turned into "disagree"; run_checks reports it.

### Verified (named) / not verified
- `python3 -m unittest tests.test_v2_customize_cleanup_render` 12 OK; `tests.test_ddf_composite_value
  tests.test_spec_reference_value_pipeline tests.test_three_view_pipeline_wiring tests.test_jeg242_blend_reference` 53 OK.
- Not verified: live site; full `make validate` (not run, per the lane brief).
- Left as dead code, not removed: `ddfNoInputsReason`'s "No sources are turned on" text and the Customize note "No sources
  on in the DDF blend" for DDF Value / projections (no longer reachable). Candidate cleanup.
