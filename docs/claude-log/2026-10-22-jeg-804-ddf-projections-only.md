## 2026-10-22 - JEG-804: Remove trade charts from DDF Value

Ticket: JEG-804. Jeremy's Q4 answer on JEG-613 (2026-10-22): "Out of DDF Value".
DDF Value = projections only (ESPN, CBS ROS, Razzball). Trade charts stay on
Indexed/VORP tabs.

### Changes

- `value-model.js`: `versionSources.blended` changed from `included` to `projI`;
  `indexBasis` changed to use `versionSources.blended` (projections only).
- `value_reference.py`: `DDF_FAMILY["blended"]` changed from `None` to
  `"projection"`; `bench_share_readout` fixed to use blended DDF Value
  (was recomputing from all included sources, diverging from engine).
- `spec_reference/value_pipeline.py`: `members["blended"]` narrowed to
  projection family; readout aligned to use `ddf_blended` value.
- `curve-widget.js`: `COMPOSITE_INPUT_KEYS` narrowed to projections only;
  `COMPOSITE_VERSIONS.ddf_value` set to `COMPOSITE_PROJECTION_INPUTS`.
- `docs/methodology.md`: VP-6.3 updated to say projections only.
- Worked example fixture regenerated for the new DDF values, Indexed factors,
  rankings and tiers.

### Verified (check named)

- `value_check compare --rerun-engine --strict`: **agree**, 1,224,171 values,
  0 mismatches across 7 sources.
- 12-combo engine sweep (13 settings): all `fixedPieIndexed=True`,
  `indexedOrderOk=True`.
- Rank guard: pass, 12 checks, 0 inversions.
- `test_value_pipeline_engine.py`: 13 passed, 1 skipped (band guard no longer
  discriminates with 1-band depth).
- `test_value_reference_worked_example.py`: 39 passed.
- `test_spec_reference_value_pipeline.py`: 39 passed.

### Claimed without confirming

- Full `make validate` and CI (left to CI on the PR).
- Front-end display effects (not in scope; v2 reads from the engine contract).
