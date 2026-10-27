## 2026-10-26 - Red main: bench-share readout test at the week 8 flip (JEG-1152)

Contract: get `tests.test_bench_share_readout_matches_reference` green again
(17 errors, `float - NoneType`), which blocked `make validate`, every PR
`preview` check and every pages.yml deploy on main. Values unchanged.

### Root cause

No code change caused it. pages.yml was green on 1edb9309 (22:55 UTC) and red
from 37644d91 (23:36 UTC), and the only change between them is chain-status
JSON. The test read two different clocks:

- the Python reference (`value_reference.Inputs.load`) uses the **UTC** date;
- the engine page (`product-data.js todayIsoDay`) uses the **America/New_York** date.

From 00:00 UTC Tuesday 2026-10-27 the reference said content week 8 and the
page still said week 7. All seven fixture sections are week 7, so the reference
excluded the four charts ("not yet published for week 8"). Since JEG-1073
(679fa54e, #919) the blended DDF Value has no projection fallback, so every
blended value, and with it the bench-share readout, was null. The engine
returned numbers, so the comparison raised `float - None`. The same test
would also fail once New York reaches Tuesday, when both sides are on week 8
against week-7 charts (null readout, then the plausibility band
`0.05 < None`).

### Fix

The test pins both sides to a day in the served data's content week:
`Inputs.load(..., today=...)` for the reference and `window.TRADE_VALUE_TODAY`
for the page, both using `tests.test_week_history._fixture_today` (the same
pin JEG-787/JEG-791 added to the other render tests). No assertion changed.

### Verified (check named)

- Before the fix, at 02:05 UTC 2026-10-27:
  `python -m unittest tests.test_bench_share_readout_matches_reference` gave
  `FAILED (errors=17)`. After the fix: `OK` (3 tests).
- In Python, `Setting('ppr', 12).result()` with the real clock: included =
  espn, cbsros, razzball; usatoday, fantasycalc, fantasypros and cbs were
  "not yet published for week 8"; blended DDF Value was non-null for 0 of 738 rows.
- `_fixture_today()` returns 2026-10-26 (week 7, the data's week).
- The diff touches only this test file and this log, so no pipeline or engine
  value can change.

### Claimed, not confirmed

- The live site loses all blended DDF Values from Tuesday 00:00 New York time
  until the week-8 charts land (no chart in I, no fallback since JEG-1073).
  That is product behaviour, not this test. Follow-up for the lead.
- The UTC/New York clock difference between the reference and the engine is a
  separate defect in `pipelines/value_reference.py`. It is left alone here to
  avoid a conflict with PR 957.

## Second test, same clock split: test_ddf_composite_value

CI `preview` on PR 979 (run 40438902494, 03:33 UTC) got past the bench-share
test, then failed `tests.test_ddf_composite_value.DdfHeldSeriesTest` (2
failures). `normalize_chart_weeks`, `normalize_served_weeks` and one test read
`content_week()`, the machine's date (UTC on CI, so week 8), while the page
read New York (week 7). The test bumped the charts to week 8, and `older_week`
then labelled usatoday week 7, which the page counted as current, so nothing
was excluded. It passed on the Mac because the Mac is on Chicago time.
Fix: a `page_week()` helper takes the New York date, as the page does; all
three call sites use it. No assertion changed.

### Verified (check named)

- `TZ=UTC python -m unittest tests.test_ddf_composite_value` at 03:37 UTC:
  the old file gave `FAILED (failures=2)`, the same two tests as CI; the new
  file gave `OK` (18 tests), also `OK` under `TZ=America/Chicago`.

## Third test: test_two_qb_direction

Running the rest of `test-core` locally under `TZ=UTC` (the suites after the
one CI stopped at) found `tests.test_two_qb_direction` failing (3 failures:
"no QB priced"). Both sides share `date.today()`, so they agree, but on week 8
against week-7 data no chart is in I, so no QB is priced. This fails in any
timezone once the real date reaches Tuesday. Both classes now pin to
`_fixture_today()`.

### Verified (check named)

- `TZ=UTC python -m unittest tests.test_two_qb_direction` at 03:39 UTC: old
  `FAILED (failures=3)`; new `OK` (6 tests), also `OK` under Chicago.
- The other 14 test-core suites after `test_ddf_composite_value`, plus the
  three node tests, passed under `TZ=UTC` at 03:38 UTC.

## Fourth round: the page itself on week 8 (04:00 UTC, lead chose option A)

At 04:00 UTC New York reached Tuesday, so the page also said week 8 against
week-7 charts and excluded every chart. CI `preview` (run 40445553560) failed
`test_v2_phone_trade_rows_render`. A local parallel sweep of test-core under
`TZ=UTC` listed 17 failing suites. The lead (Ba-Nana orchestrator) authorized
option A: pin the page clock in test setup only. Option B (a grace window
when a new week has no published charts) goes to Jeremy separately.

Fix: `tests/_render_env.pin_data_week_script()` returns the JEG-787/791 init
script (`window.TRADE_VALUE_TODAY = _fixture_today()`). Each `new_page` in 16
suites now adds it. No assertion, value code, engine, pipeline, fixture or
dist change.

### Verified (check named)

- Serial `TZ=UTC python -m unittest tests.<suite>` at 04:20-04:39 UTC, one at
  a time: all 17 OK (superflex_publisher_values, superflex, rank_guard, the
  eight v2_phone_* suites, launch_front_door, week_history, value_overrides,
  v2_desktop_menu_render, missing_section_render, search_players_universe).
- `test_week_history` passed with no change, so its failure in the parallel
  sweep was noise (concurrent dist rebuilds).
- `test_v2_phone_trade_rows_render` without the pin, run alone: 2 errors (no
  #v2Compare rows); with the pin: OK.

### Claimed, not confirmed

- The other 15 previously failing suites were seen failing only in the
  parallel sweep, not one at a time without the pin.
- `tests.test_v2_waterfall_render` (the second v2-render CI suite) failed on
  CI run 40450942126 at 02d2bb95 (no player data: `reading 'player_key'`).
  With the pin added at its three `new_page` calls: `TZ=UTC` OK (7 tests) at 04:52 UTC.
- `tests.test_v2_phone_fallback_font_render` failed CI preview at 882640ea
  (run 40451964548: `'#player-values' not found`), same cause; pinned at its
  two `new_page` calls. Not run locally (needs DejaVu Sans, not installed on
  the Mac): claimed, confirmed only by the next CI run.
- `tests.test_static_export` fails locally only because `dist/` was restored
  to the committed copy without a rebuild; CI rebuilds first and passed it on
  81f8d5f2. Not a date problem, not changed.

## Stopped: value-check-compare disagrees in the week-8 state (not a test clock bug)

At fdceef59 CI `preview` (run 40452846042) passed all of test-core and
v2-render passed, then `make value-check-compare` failed: engine vs Python
reference disagree on fantasypros (5 values, engine 0 vs reference up to
0.122; ppr/10, half_ppr/12, standard/14; player keys 1502, 4086). Both sides
already get the same `today` (UTC date), so this is not a clock split.

### Verified (check named)

- `python3 pipelines/value_check.py compare --rerun-engine --strict --today 2026-10-26`:
  verdict agree, 1,230,125 values, 0 mismatches.
- Same with `--today 2026-10-27`: verdict disagree, fantasypros 5 mismatches,
  the same as CI.

So in the "new week, charts not yet published" state (the live state now)
engine and reference price a held or unpublished chart differently. Pinning
`--today` would change the Makefile gate, not test setup, and would hide a
real fidelity disagreement, so it was not done. PR 979 is not merged.

## Resumed 2026-10-27: the value-check disagreement was an engine port bug (JEG-1152)

Root cause: the JEG-969 promotion model (#867) differs between the engine and
the reference. `value_reference._apply_promotion_model` gives a bench player
with no lineup share but value above waivers a promotion bonus
(`start_worthy_part = avail * vorp * bonus_share`). The engine's
`esApplyPromotionModel` had no such branch and left him at 0. The week-8
lineup window put two such FantasyPros/FantasyCalc WRs (keys 1502, 4086) at
that depth, so the disagreement showed only from 2026-10-27. It was not the
JEG-1156 publish-lag question and not a clock bug. The engine now follows the
reference (the authority); the reference is unchanged.

Value-math change (engine only, tiny: these values moved from 0 to at most
0.12), so the merge waits for the lead's sign-off.

### Verified (check named)

- `python3 pipelines/value_check.py compare --rerun-engine --strict` after
  `make reference sync`: `--today 2026-10-26` agree (1,230,125 values),
  `--today 2026-10-27` agree (713,525 values). Before the fix 2026-10-27
  disagreed (fantasypros 5), as in CI.
- `tests.test_promotion_model_parity` (new, in test-core): passes with the
  fix, 5 failures against the pre-fix value-model.js.
- `tests.test_value_pipeline_engine`, `tests.test_spec_reference_value_pipeline`,
  `tests.test_rank_guard`: OK locally.
- `make values-explainer MARK_REVIEWED=1`: narrative has no promotion text, so
  unchanged; logic marked reviewed.

### Claimed, not confirmed

- The main pages.yml rank-guard failure ("no Indexed values or native ranks")
  is the unpinned page clock that this branch already pins
  (`_render_env.pin_data_week_script`); confirmed only once this merges and
  pages.yml runs.
