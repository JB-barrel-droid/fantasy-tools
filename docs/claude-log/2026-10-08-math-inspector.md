## 2026-10-08 - Math inspector: every input and step of the value math (feat/math-inspector, lane 11)

Jeremy: "surfaces to see consolidated data input in a clear way to evaluate the
math that is going on."

### What was built
- Internal page `modules/math-inspector.html` (noindex, nofollow, no
  canonical, linked from no public page). Source `app/inspector/`
  (shell.html, math-inspector.js, math-inspector.css); built on every
  `make sync` by `pipelines/build_inspector_page.py` from
  `dist/classic/index.html`, the same way build_v2_page reuses the engine: the
  chart page runs unchanged off-screen. Generated files are gitignored.
- Controls: scoring, teams, every roster spot (incl. bench), bench share,
  source, position. They call the engine's own setters; the page re-renders on
  `trade-value-rows-change`.
- Sections: View checks (Indexed totals vs anchor, VORP vs waivers totals vs
  budgets, Adjusted group totals vs budget x 70-factor, the engine's own
  fixed-pie guard); 1 Inputs (provenance and content week per source, raw
  saved values in native units, identity rows not resolved to a charted
  player); 2 Translation (rostered counts, waiver line and method, above
  waivers in native units, implied position and starter/bench weights, each
  player); 3 Indexed (pie split by position x starter/bench beside the
  anchor's on the same players, points and shares, every player x series);
  4 VORP vs waivers (per-chart factor, each player side by side); 5 Adjusted
  values (our weight per group, the chart's own weight, normalization factor
  per group, each player with a recomputation check); 6 one-player drill-down
  (every source x every step, prior week via getPriorWeek and the change).
  CSV/JSON download on every table, plus the whole snapshot as JSON.
- Engine: `TradeValueCurveControls.getInspection()` (read-only). It reads
  the same maps and makes the same ValueModel calls as the chart; the two
  diagnostic records it touches (lastPublishedView, lastPublishedDerivation)
  are swapped for copies and restored. `derivedPublishedSourceMap`'s input
  building moved into `derivePublishedFor(key)` (pure extraction, shared with
  the inspector). ValueModel: `derivePublishedSetup` also returns
  `translation`; `derivePublishedViews` also returns per-source `budgets`,
  `roles`, `translation` -- echoes of existing intermediates, no value math
  changed.

### Verified (check named)
- `tests/test_math_inspector.py` (added to `make test-core`): inspector
  tables == `getAllRows()` for every player x series in all three views
  (engine view switched by its own tab) at 12/Full PPR (saved setup),
  10/Half PPR and 14/Standard WR2 bench 8; rendered cells == table data; at
  the derived settings the shown intermediates rebuild every shown VORP vs
  waivers and Adjusted value (|diff| <= 1e-6). Passes.
- Guard discrimination (`test_guard_fails_on_broken_inspector`): an inspector
  showing the saved 12-team Indexed values at 10 teams fails with 585
  mismatches; one showing the browser derivation instead of the saved VORP
  view at 12/PPR fails with 562; one recomputing Adjusted instead of reading
  the engine fails with 537. The first version of the Indexed mutation
  (browser derivation at the saved setup) was NOT caught, because the browser
  derivation reproduces the saved Indexed values exactly there; replaced with
  the saved-values-at-10-teams mutation.
- First parity run found a real inspector defect: it listed players the chart
  never shows (ESPN 0 for players in no series). Fixed by reading the engine's
  own row universe.
- 12-combo x 3-view headless sweep, base dac0ff2 build vs this branch build,
  same fixture: getAllRows, fixedPieIndexed, sourceScaleAgreement and
  sourcePeaks identical in 36/36 (0 differing). fixedPieIndexed true
  everywhere; sourceScaleAgreement false in 33/36 on BOTH builds
  (pre-existing; that check was retired on main the same day, GAP-026).
- `make sync` + `CHROMIUM_PATH=... make validate`: exit 0 (includes
  tests.test_math_inspector).

### Measured with the inspector (data as of base dac0ff2)
- Indexed totals vs the anchor on shared players (published charts):
  ppr/12 USA Today +5.2%, FantasyCalc -23.0%, FantasyPros +22.4%, CBS -11.9%;
  half/10 +15.3/-12.6/+25.6/-4.9%; standard/14 -3.0/-31.1/+8.2/-19.0%.
  CBS ROS, Razzball and the *_adjusted series equal to 1e-12.
- VORP vs waivers: derived views equal the target total at every setting;
  the saved views at ppr/12 (FantasyCalc / FantasyPros / USA Today) are
  358 / 284 / 389 points short.
- Adjusted values: saved views' group totals all differ from budget x 70
  factor; derived views match except groups where the chart has no player
  above waivers (budget dropped): ppr/12 CBS QB bench; standard/14
  FantasyPros QB bench, CBS QB bench, CBS WR bench.
  Logged as GAP-VIEW-INVARIANTS-MEASURED for the views-audit lane.

### Claimed, not confirmed
- The views-audit lane had not pushed a branch when this was written, so the
  inspector does not surface its diagnostics; the "View checks" section is
  the inspector's own measurement. Whether "anchor sum over shared players
  with the anchor's roles" is the right Indexed reference is for that lane.
- Inputs > Identity is computed from the served fixture (source name ->
  player_key -> charted player); it does not read Supabase review queues.
- The live URL has not been checked (branch not merged).
