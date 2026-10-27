## 2026-10-25 - JEG-1108 finish: test updates for the new fit definitions, label distribution

Contract: bring the tests and leftovers in line with the rewritten fit rule (Natural / Market supported / Force; Value fit retired) and measure how the labels split on the 20-team reference league. Test edits below are only because the definition changed, not to turn anything green.

### Test edits and why (each one follows a definition change, none loosens a check)
- tests/test_v2_finder_fit_render.py: the fit line is now one of "Natural fit", "Market supported" or "Force fit" (Value fit is retired), each followed by an optional viability suffix (" · High viability"); the tier order is natural, market supported, force. The old rule "every non-force line names both views" is narrowed to natural lines: a Market supported line is defined by the trade charts alone, so it reads "the trade charts favor them" and may not mention DDF Value. A new check requires that wording on every market supported line.
- tests/league_harness.cjs (run by tests/test_v2_league_units.py): the overall label is the finder's label, so the old spec 4.3 truth table (natural/value/market/force from our label, chart edge and their label) no longer describes the code. Replaced by: (1) the finder's label is returned as is when present; (2) the fallback table for callers without it; (3) every real row's overall equals its fit label and "value" never appears. Row shape now allows our fit "partial" and their fit "favorable" (renamed from "fills"). The tier-order test drops the value tier. The filter test uses naturalMarket and requires it to equal everything except force.
- tests/test_v2_league_units.py: mutation "overall fit always natural when it fills" had a stale anchor (the code it broke is gone); replaced by "overall fit ignores the finder's label" and shown to be caught by test_opportunities_fit_label and test_opportunities_fit_label_rows.
- app/v2/opportunities.js, app/v2/finder.js: comments that still described value / market-only tiers corrected (no logic change).
- tests/test_v2_finder_fit_render.py (group check): the finder now lists at most two groups per received player and folds the rest into a "N more for <player>" note (JEG-885), so "shown edges equal the search's edges" no longer holds by definition. Replaced by: every shown edge is one of the search's edges (none invented or re-valued) and the number of unlisted search groups equals the sum of the "N more for" notes (none lost silently). New guard mutant: folded groups not counted in the note, shown to be caught.
- tests/test_v2_league_oppanel_render.py: the viability slot used to say "not shown here yet". It now carries "<fit label> · <High|Medium-high|Medium> viability"; the test requires that full pattern (so "not assessed" fails). Before the fix below it failed with "not assessed", which is the negative test.
- tests/test_v2_league_top10_render.py: with ~55 Natural rows the natural filter now shows a full page, so the filtered-count check reached a `.split(" of ")[1]` that crashed on the guard's "count line dropped" build instead of reporting an error. Parsing made safe (regex); the check itself is unchanged.
- Makefile test-core: the fit unit tests (test_v2_finder_fit, trifit, balance, league_units) were wired in no target; now wired, plus the diagnostic below.

### New: tests/node/fit_diagnostic.cjs
Deterministic, pure Node. Builds the 20-team fixture league (tests/fixtures/league/fixture-20team.json, same synthetic engine rows and 12-team depth as tests/league_harness.cjs, team 0 = you), runs the real opportunities and finder code, counts overall labels. `--assert` also fails if rows are missing, counts do not add up, a Value label appears, or Natural, Market supported or Force is empty. Pass another checkout's app/v2 as the first argument to measure an older build.

Distribution, 189 opportunities:

| label | before rewrite (fe/JEG-1093-finder 81507d16) | after |
|---|---|---|
| Natural | 2 (1.1%) | 55 (29.1%) |
| Value | 91 (48.1%) | retired |
| Market (old: you gain, charts say they lose) | 4 (2.1%) | Market supported (new: charts favor them): 97 (51.3%) |
| Force | 92 (48.7%) | 37 (19.6%) |

The "before" run reproduces the earlier investigation exactly (2 / 91 / 4 / 92).

### Verified (check named)
- Before table: `node tests/node/fit_diagnostic.cjs <old app/v2 from git archive of origin/fe/JEG-1093-finder>` printed 2 / 91 / 4 / 92 of 189.
- After table: `node tests/node/fit_diagnostic.cjs --assert` printed 55 / 97 / 37 of 189, assertions passed (0.1 s).
- Negative tests of the diagnostic: against the old build it fails ("the retired value label appeared"); with finder.js forced to label everything force it fails ("no Natural rows"); with the Natural test forced false it fails (same message).
- `python -m unittest tests.test_v2_finder_fit tests.test_v2_finder_trifit tests.test_v2_finder_balance tests.test_v2_league_units tests.test_v2_finder_import`: pass, including the mutation checks.
- grep for "Market fit", "Market Only Fit", "Value fit" over the repo (excluding dist, logs): only comments that say the old name is retired remain; no user-visible copy.

### Second measurement: the browser league with real engine values
The 20-team fixture league through the real page (tests/_league_render seed, real engine values, scripted check, not committed): 89 opportunities, Natural 4 (4.5%), Market supported 0, Force 85 (95.5%). Per test: roster construction passes for both teams on 64 of 89, their Trade chart average within the noise floor or better on 87, your DDF Value total rising beyond the noise floor with starters not worse on only 6. Natural = 4. The binding test on real values is the "your total must rise beyond the noise floor" one (floor is the larger of 0.05 and 1 standard error of the moving players; shown as "noise floor 2.0" on the page). Posted to JEG-1108 as a multiple-choice question; no threshold was changed.

### Bug found and fixed
- app/v2/league.js viabilityText: the detail panel always read "Viability: not assessed (insufficient data)" because it passed rosters without the Trade chart average series to viabilityLabel, so their lineup looked empty. Rosters now carry the chart average (F.withChartAverage) first. Seen failing in test_v2_league_oppanel_render before the fix, passing after.

### Render tests (browser, run one at a time after another lane's render loop ended)
Pass: test_v2_find_split_render, test_v2_finder_render, test_v2_finder_collapse_render, test_v2_league_render, test_v2_league_tables_render, test_v2_league_basis_render, test_v2_league_oppanel_render (after fix), test_v2_league_top10_render (after fix), test_render_sweep_coverage, test_v2_finder_fit_render guard test (all mutants caught).
Fail identically on origin/fe/JEG-1093-finder (checked in a separate checkout), so not caused by this change: test_v2_finder_fit_render::test_fit (thin-roster case: "no star RB and two RB2s in the data", the published data no longer has a star RB whose two RB2s three charts price as even), test_v2_finder_eval_render (table cell reads "OK" where a number is expected), test_v2_finder_groups_render ("no group had a full give side with a spare player"), test_waivers_render (nav tab list; nav lane).
Market supported on screen (scripted browser check on the 20-team league; the real data has no Market supported rows, so the finder's market test was forced true for that run): table cell "Market supported", Their team fit "Trade charts favor them", filter option "Natural and market supported", detail panel "Market supported: the trade charts favor them (...)" and "Market supported · Medium viability". No page text matched Market fit, Market Only Fit or Value fit.

### Claimed, not confirmed
- The 20-team fixture in the diagnostic uses synthetic engine rows (same as league_harness); the in-browser 20-team league uses real engine values and gives a different split (4 Natural of 89, see above). Neither is a production league.
- `PATH=<venv>/bin:$PATH make test-core` exited 0 (434 unittest targets) with the additions to the Makefile; the render targets outside test-core were run by hand as listed above.
