## 2026-10-22 - JEG-868 / JEG-869 Trade targets: chart as Our value vs All charts, single-chart heading

- Problem (JEG-868, live 2026-10-22): Our value = a trade chart with Compare
  against = All trade charts threw `Cannot read properties of undefined
  (reading 'value')` at renderTargetTable and left the previous selection's
  lists on the page. Reproduced locally on the built dist (USA Today,
  FantasyPros; CBS is held in the pinned-holds fixture so it is blocked, no error).
- Root cause: `app/v2/v2.js` collectTargets built `used` from
  `chartsToCompare` with our own chart still in it, while `targets.js`
  buildTargets (#807, effectiveCharts) priced only the other charts. The
  render iterated `targetsView.used` and read `p.cells[ourChart].value`.
- Fix (v2.js, targets code only): `used` and `prior` drop our own chart when
  Our value is a chart; a Compare pick equal to Our value falls back to "all"
  inside collectTargets (before the lists are built, not only when the
  controls redraw); the "all" option reads "All other trade charts" when Our
  value is a chart and the headings/sub-lines say "the other charts"; each
  list's render is guarded: on an error the list is cleared, the empty state
  says it could not be built, and the error is rethrown after both lists are
  handled (never a stale render, never a hidden error).
- Fix (JEG-869): with one chart compared the headings read "Sell: <name> pays
  more than we would" / "Buy: <name> pays less than we would", the sub-line
  leads with "Against one chart: <name>." (the footnote already did); the
  empty-state copy does not claim 2 or more charts.
- Tests: `tests/test_v2_targets_combos_render.py` (new) cycles every enabled
  Our value x every enabled Compare against option at 1440x900 and 390x844,
  fails on any uncaught pageerror, checks the engine state and the rendered
  lists match the selection (never the previous one) and the copy matches the
  mode. Negative-tested against 6 mutations: the JEG-868 bug reintroduced
  (caught as a page error), the bug with the guard disabled (caught as stale
  lists), the JEG-869 heading and sub-line reverted, the "All other" label
  dropped, the self-compare fallback removed. `tests/test_v2_targets.py`:
  chartAsOursAll harness (cells are exactly the other three charts).
- Verified locally: see the PR body (named runs).
- Screenshots: /Users/botcomp/code/fantasy-tools-selfhost-notes/jeg-868-{before,after}-usatoday-all.png,
  jeg-869-{before,after}-ddf-vs-usatoday.png.
