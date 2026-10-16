## 2026-10-16 - JEG-677 Trade targets Check 1: market consensus

Contract: Check 1 ranks by the median of the indexed charts minus our value; eligible with 2+ charts and a strict majority on the same side; rows show the consensus, "N of M charts agree" and one dot per chart; default Our value is DDF Projections (reverses the JEG-455 default; decision taken from Jeremy's JEG-461 / JEG-476 rules, recorded on the ticket).

### Changed
- `app/v2/targets.js` (module, pure): `marketConsensus` replaces `marketAverage`; best-single-chart gap removed; `OUR_KEYS` starts with `ddf_value_projections`; `weightCheck` keeps DDF Value via `DDF_VALUE_KEY`; `buildTargets` also returns `players`.
- `app/v2/v2.js`: minimal hook only (column labels, `targetBest` / `agreeNode`, list copy, dead `bestChartNode` removed); `v2.css`, `shell.html` footnote.
- Tests rewritten for the rule: `test_v2_targets.py` (independent Python reference, 20 mutations), `test_v2_targets_render.py` (expected lists recomputed from engine rows; probes simulated on the projections series), `test_espn_zero_badge_render.py` and `test_below_leg_zero_render.py` (ESPN-0 players list only when the consensus rule holds; assertion changed because the rule changed).

### Verified (check named)
- `tests.test_v2_targets`: lists, order, agree counts and dots equal the reference for four series; all mutations caught.
- `tests.test_v2_targets_render` numbers path at 1440/1366/1024/390: no errors beyond the ones already red on main (week-6 badges, divergence chip in header sub-label, fold, Razzball unavailable).
- `tests.test_espn_zero_badge_render`: green.

### Claimed, not confirmed
- Render mutation "prior-week badge removed" crashes the page rather than failing a check (same on main; not touched).
- `test_v2_ddf_versions_render` and `test_below_leg_zero_render` guard tests were red before this change for data reasons (disabled charts version, week 6).
- No screenshot review of the new dots.
