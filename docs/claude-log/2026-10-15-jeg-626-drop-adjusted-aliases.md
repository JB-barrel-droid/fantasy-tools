## 2026-10-15 - JEG-626 v2 drops *_adjusted alias series

Contract: remove the "Trade charts (adjusted)" group and every `*_adjusted` alias read in app/v2/v2.js; v2 reads the raw chart series.

### Changed
- app/v2/v2.js: removed the `adj` series group, `_adjusted` branches in seriesGroup/groupSeriesName/sourceMeta, the "adjusted" table group and the KIND map (non-vorp, non-indexed series are projections). The legacy engine still lists the `*_adjusted` aliases, so `sourceInfoWithFreshness` and `collect` filter them out (`isEngineAlias`).
- Tests (deliberately retired by JEG-539/626): test_v2_how_render, test_v2_offer_render, test_v2_panels_render, test_v2_waterfall_render no longer classify or select `*_adjusted` keys; they use the raw chart keys.

### Verified (check named)
- `make sync` exit 0 after rebase on origin/main.
- tests/test_v2_*.py plus view-switch and kdst-wiring suites: 63 passed, 13 failed. The same render tests (e.g. test_v2_ddf_versions_render, test_v2_risers_render) fail identically with main's v2.js and tests swapped in (8 of 9 failed), cause: the DDF charts/projections version checkboxes are disabled ("not yet published for week 6") in this checkout's data.

### Claimed / not confirmed
- Full `make validate` stops at tests/test_asset_load_retry.py (2 of 3 fail on main too, same week-6 cause); remaining suites not run. `value_check compare --rerun-engine` reports availability mismatches on ddf_value_charts_prior, independent of the front end (engine vs reference).
- tests/test_score_lineup_values.py collection error (`expected_starts_model.ROSTER`) is the JEG-562 lane.
- Legacy engine (curve-widget.js, index.html) still carries `*_adjusted`; out of scope.
