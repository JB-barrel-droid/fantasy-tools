## 2026-10-16 - JEG-677 follow-up: Trade targets default Our value is DDF Value; consensus basis checked

Decision (Jeremy, 2026-10-16): "DDF decides who we want and don't want", so the default Our value is DDF Value (the blend), not DDF Projections (PR 630). Market side = consensus of the INDEXED trade charts plus each chart, to find value and offer-acceptance opportunities.

### Changed
- `app/v2/targets.js`: `OUR_KEYS` starts with `ddf_value` again (other versions kept, order as before PR 630); each consensus dot carries its chart's value.
- `app/v2/v2.js`: dot tooltip reads "<Chart> (indexed) 17.4: above our value"; `data-value` on the dot.
- `docs/feature-contract.md` GL-08, TT-03, TT-04, TT-08; `docs/v2-design-notes.md` default note.
- Tests: `test_v2_targets.py`, `test_v2_targets_render.py`, `test_v2_contract_render.py` (tt04 only).

### Basis check (verified by reading code)
Chart keys `usatoday`/`fantasycalc`/`fantasypros`/`cbs` in the engine rows are the combo_reindexed (Indexed) series; the adjusted ones are `<chart>_adj_values` and are not in `CHART_KEYS`; `collectTargets` blocks the tab outside the engine's Indexed view. So PR 630 already used Indexed; no basis switch was needed.

### Test changes and why (assertions changed because the decided behavior changed, not to go green)
- `test_v2_targets.py`: default key asserted `ddf_value` (was projections); `OUR_KEYS` order asserted DDF Value first; named default lists now buy [6, 37, 32] (player F is a consensus buy under DDF Value, absent under projections because the fixture ROWS carry no projections value) and default omitted = 2; added a DDF Projections run and a dot-value assertion. Mutations: "default moved off DDF Value", "DDF Projections dropped", "dot value not the indexed chart value" added.
- `test_v2_targets_render.py`: default series DDF again (probes simulated on `ddf_value` row-level fields as before PR 630; PROJ stays in the picker run); added dot-value/title check.
- `test_v2_contract_render.py` `tt04`: the old check required the row to name the single chart with the largest gap (the behavior JEG-677 removed). Now requires `best.chart == consensus`, "N of M charts agree" with 2+ charts, a strict majority and one dot per chart. `gl08`/`tt03` already asserted `ddf_value`; they were red on main because of the PR 630 default and are green again by this change. `tt07` is now vacuous for consensus rows (not changed; the waiver rule is pinned in test_v2_targets and the render test).

### Verified (check named)
- `tests.test_v2_targets`: green (2 tests, 21 subtests).
- `tests.test_v2_targets_render` numbers path: with the repo's current data only 2 charts are available, so the probes that need a 3-chart target fail ("no sell target with two charts to simulate rows on"). Re-ran once with a TEMPORARY local `of >= 2` edit (reverted): the DDF Value, DDF Projections and ESPN runs, indexed dot values, consensus lists, tiers and counts passed; remaining reds were the probes (2 charts), fold/filter-wrap, and CBS ROS / Razzball unavailable (week-6 data). `test_guard_fails_on_broken_builds` green.
- `make sync` run.

### Claimed, not confirmed
- Contract live-line results: see the PR body.
- No screenshot review of the dot tooltip.
