## 2026-10-26 - JEG-1129 MARKET_KEY collision (be/jeg-viability-rework / PR #960)

Contract: make PR #960 mergeable by separating the engine's `ddf_value_charts` (MARKET_KEY, what the
viability rule reads) from the plain chart mean that `withChartAverage` writes (CHART_AVG_KEY =
`chart_avg`), so waivers' DDF Value noise floor and the other `chart_avg` consumers behave as on
origin/main. Value math, thresholds, fixtures and `supabase/**` are untouched.

This entry was written by an OpenRouter **deepseek-v4.1-flash** run (T2/T3). Its output is untrusted
until a Claude T1 review; the merge gate is the lead's.

### Call sites, and what each now reads

In `app/v2/finder.js`:

| Site | Reads | Why |
| -- | -- | -- |
| `withChartAverage` (~382) | writes `CHART_AVG_KEY` | the display series is the plain chart mean; it must not overwrite `ddf_value_charts` (the bug) |
| `scoreChips` (~1117) | `CHART_AVG_KEY` | rows come from `withChartAverage([row], charts)` |
| `sideAssessment` market view (~1151) | `CHART_AVG_KEY` | `marketRows = withChartAverage(rows, charts)` |
| `assessmentTable` "Trade chart average" view key (~1172) | `CHART_AVG_KEY` | renders `sideAssessment`'s market view (rows with `chart_avg`) |
| `valueNoise` (~612) | both keys | `key === MARKET_KEY \|\| key === CHART_AVG_KEY` -> standard error of the chart values |
| `api` export (~833) | adds `CHART_AVG_KEY` | `MARKET_KEY` stays exported |
| `viabilityLabel` (`mk = MARKET_KEY`, ~196) | `MARKET_KEY` (unchanged) | viability path reads raw engine rows |
| `fitContext` `marketKey` (~1266) | `MARKET_KEY` (unchanged) | `lineupContext` passes raw engine rows |
| `viewKey` (~1685) | `MARKET_KEY` (unchanged) | find-trades / roster-impact view over raw engine rows |
| `lineupContext` (~1675) | no local mean (unchanged) | comment already said `ddf_value_charts` is engine-computed |
| `balanceCounts` (~244) | literal `"chart_avg"` (unchanged) | its callers pass rows through `withChartAverage`, which writes `chart_avg` again after this fix |

In `app/v2/waivers.js`: destructures `CHART_AVG_KEY` instead of `MARKET_KEY` and uses it in `viewFor("market")`,
`viewValueOf`'s usable-min check, `marketOf`, and `contextFor`'s "is the market view available" filter — its market
view is the plain chart mean, as on origin/main.

`league.js`, `opportunities.js` and `team-summary.js` keep their own `MARKET_KEY = "chart_avg"`; they call
`F.withChartAverage` and read `chart_avg`, so they work again with no edit.

### Test-source anchors updated (rule unchanged)

Three mutants match exact source strings that contained the identifier `MARKET_KEY` in `waivers.js` /
`withChartAverage`; the JEG-1129 rename invalidates the anchor while the rule each mutant breaks is identical:

- `tests/test_waivers_math.py` "zero market shown": anchor `row.values[MARKET_KEY] ...` -> `row.values[CHART_AVG_KEY] ...`
- `tests/test_waivers_views.py` "no market price read as a price": anchor `key !== MARKET_KEY` -> `key !== CHART_AVG_KEY`
- `tests/test_v2_finder_impact.py` `AVG`/market-lineup harness: reads `F.MARKET_KEY` -> `F.CHART_AVG_KEY`

No expected value or assertion changed. This is the one deviation from the brief's "do not edit
test_waivers_math assertions or fixtures": the fixture's tau expectation is untouched and was the failing check.

### Verified (check named)

- `python3 -m unittest tests.test_v2_chart_avg_key` (new) passes; with `app/v2/finder.js` and
  `app/v2/waivers.js` stashed (i.e. without the fix) the same module fails 4 of its checks, including
  "ddf_value_charts overwritten: 13, want 50" and `MARKET_KEY / CHART_AVG_KEY: ['ddf_value_charts', None]`.
- `python3 -m unittest tests.test_waivers_math` — OK (the reported `[qb-streaming] Mo MarginalQB` tau failure is gone).
- `python3 -m unittest tests.test_waivers_views` — OK.
- `python3 -m unittest tests.test_v2_targets` — OK.
- `python3 -m unittest tests.test_v2_finder` — OK.
- `python3 -m unittest tests.test_v2_finder_balance` — OK.
- `python3 -m unittest tests.test_v2_finder_projection_noise` — OK.
- `python3 -m unittest tests.test_v2_finder_fit` — OK.
- `python3 -m unittest tests.test_v2_finder_impact` — OK (after the harness key update above).
- `python3 -m unittest tests.test_v2_finder_trifit` — OK.
- `node tests/node/viability_check.mjs` — 29 passed, 0 failed.
- `RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_league_tables_render` — Ran 2 tests, OK (~3.5 min).
- `make test-core` could not run: `make` is not installed in this environment. Running the 89 modules in the
  `test-core` recipe one by one was started and exceeded the 10-minute budget, so it is NOT reported as run; the
  modules this change touches are the named suites above and they pass.

### Claimed, not confirmed

- Browser rendering of the Trade chart average column/views in Find a trade, league tables, opportunities and
  team summary (only the python/node logic and mutant checks above were run here; no live page check was made).
- That no other page reads `ddf_value_charts` off a `withChartAverage` result; checked by `rg` over `app/` and
  `supabase/` (no hits outside finder.js), not by a live render sweep.
