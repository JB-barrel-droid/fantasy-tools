## 2026-10-25 - JEG-1081 PR 1: projections noise floor

Contract: add the DDF Value (projections) branch to `valueNoise` in `app/v2/finder.js` (standard error of the mean of ESPN, CBS rest of season and Razzball), export `PROJECTION_KEYS`, no UI and no change to any existing branch or constant (spec v2 section 3c, build plan PR 1).

### Verified (check named)
- `tests.test_v2_finder_projection_noise`: SE for three, two, one and zero readings, no leakage between chart and projection branches, zeroing one source raises noise, existing DDF Value and chart branches unchanged, `teamFit` tau under the projections key uses the new noise, exports present.
- Same file, `test_checks_fail_on_broken_builds`: seven broken copies of finder.js (branch removed, wrong source set, sd not SE, population variance, single reading allowed, charts read for projections, DDF Value branch dropped) each fail the checks.
- `tests.test_v2_finder_fit`, `test_v2_finder_impact`, `test_waivers_math` pass unchanged.
- Distribution on `dist/consolidated-values.json` (PPR/12, combo_reindexed): projections SE mean 0.743, p90 2.631 (n=545); chart SE mean 1.906, p90 3.361 (n=179).

### Claimed, not confirmed
- Threshold stability on a held-out week (the 25% rule): the consolidated file holds week 7 only. Deferred to PR 2.
- Whether the per-source `espn`/`cbsros`/`razzball` values the page loads sit on the same point scale as `ddf_value_projections`; the spec uses them as loaded. Not checked in the browser.
- Nothing calls the new branch yet (PR 2 does); no user-visible change in this PR.
