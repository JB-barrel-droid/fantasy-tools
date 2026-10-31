# JEG-1385: get-values prices this week on the VP-1.2 included set (2026-10-30)

Cloud Claude session, on Jeremy's instruction (he chose to hold the get-values and mcp redeploy for
JEG-1029 until this is fixed, then deploy once). Branch `claude/JEG-1385`, from main b5f35fca.

## Live check (before any change)

- The live connector (get_values, ppr/12) serves Week 8 only, with all seven sources included
  (espn, cbsros, razzball, fantasycalc, usatoday, fantasypros, cbs), no missing sources.
- The week history from the 2026-10-30 16:58 UTC automated rebuild (`data/history/`) has a Week 7
  entry for all seven, with values at standard, half PPR and PPR (charts: natives per scoring;
  projections: ppg triples).
- `buildPipelineInput` + `savedNatives(week 7)` at ppr/12, half_ppr/10 SF, standard/14, ppr/12 SF,
  half_ppr/12, standard/12: no included source is unpaired. Live numbers are not wrong today.
- It bites when a source the page counts has no Week N-1 saved (a new source, a failed save, or an
  explicit earlier week whose N-1 lacks a source: Week 2 has no razzball or cbsros, Week 3 no cbsros).

## Fix

- `supabase/functions/get-values/pipeline.ts` `buildPipelineInput`: after the eligibility loop, when
  the week and the history index are known, I = the included sources with Week N-1 saved
  (`savedNatives`). When I is non-empty and smaller than the included list, the others keep their
  values with status "excluded" (shown, never counted, as `runPipeline(natives, I)` on the page) and
  `included` becomes I. When no source is paired, nothing changes (VP-1.2's fallback). Same rule as
  `priorBlock` (analysis.ts) already used for the prior side.
- `supabase/functions/get-values/index.ts`: Week N-1's document is loaded before the input is built
  (it was only loaded for include=prior, after the main run, so the fix would otherwise never see it).
  A failed read leaves the document unloaded, which reads as no source paired (old behaviour).
- `priorBlock` needs no change: its unpaired branch no longer fires, since `input.included` is I.

## Evidence

- New `tests/test_connector_analyses.py test_unpaired_source_prices_this_week_on_included_set`, rows
  from the sentinel fixture `tests/fixtures/get_values_pairing_sentinels.json` (ppr/12 FantasyCalc,
  half_ppr/10 superflex Razzball, standard/14 CBS, each with that source's Week 7 entry dropped):
  get-values' values, series, prior and audit (pie, included set, position counts) against
  `value_reference` to 1e-6. On main: 3 failures (the dropped source is in get-values' included set).
  On the branch: passes. The existing unpaired-prior test now reads the current side from the series
  block when no `current_values` is given (get-values' own run is the run on I).
- Every source paired: the runner's full output (values, week, series, prior, audit) is byte-identical
  between main and the branch at ppr/12, half_ppr/10 SF and standard/14 (1,005,638 / 967,923 /
  1,069,728 bytes).
- Before/after (main vs branch, Week 7 entry dropped; the branch equals the page/reference):
  - ppr/12, FantasyCalc dropped: 195 of 741 players change, max 5.0. Josh Allen 31.2 -> 26.1,
    Jaxon Smith-Njigba 67.0 -> 62.9, Chuba Hubbard 38.3 -> 41.6, CeeDee Lamb 52.4 -> 49.2,
    Rhamondre Stevenson 18.6 -> 21.7, Trey McBride 30.6 -> 27.7, Jahmyr Gibbs 75.0 -> 72.3.
  - half_ppr/10 SF, Razzball dropped: 171 change, max 3.0 (Jahmyr Gibbs 61.5 -> 58.4).
  - standard/14, CBS dropped: 217 change, max 4.9 (Jaxon Smith-Njigba 62.0 -> 57.1).
  - Today's live data: no player changes (every source paired).

## Review corrections (JEG-1390, child of JEG-1385)

Independent Claude review of f7079ab: request changes. Each finding, with failing-before (f7079ab with
the new tests copied in) and passing-after (this head):

1. Pairing used another build's history. Now it runs only inside the week view (which needs this
   build's history), as the page's `servedWeekOf` and the reference's `same_build` do. Sentinel row
   `ppr-12-fantasycalc-other-build`: f7079ab fails (FantasyCalc left out of the included set, 195
   values off by up to 5.04 per the review); now passes, values, series and audit match the reference.
2. A source with no served week counted as paired. Now it needs an integer served week. Row
   `ppr-12-cbs-no-served-week`: f7079ab fails (CBS counted); now passes. priorBlock gives that
   source's series no pair either (it showed one before; caught by the same row).
3. The unpaired source's reason is now "no prior week: <why>" in sources_excluded and audit.excluded
   (`excludedSources`, used by index.ts and the runner). f7079ab fails all three original rows on the
   new reason assertion.
4. priorBlock now pairs nothing against another build's history (main and f7079ab: available; now
   unavailable, "the history index belongs to a different build of the values"). addAnalysis no
   longer re-reads Week N-1, so the prior block and the values are always priced on one included set.
5. Byte identity stays a recorded check rather than a committed golden (a golden of main's output
   would break on every data refresh). Re-run on this head: identical to main at all three settings.

Other checks on this head: `tests.test_connector_analyses` 5/5; node get-values checks (handler,
value context, week, drift, connector round trip, rate limit) ok; `tests.test_endpoint_parity` and
`tests.test_edge_functions_parse` ok (browser parts skipped). `jeg_1061_logging_contract.mjs` fails
the same way on main (it waits on #1210).
