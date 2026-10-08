## 2026-10-08 - Projection-series curve starts above the ESPN anchor (investigate/proj-peaks)

Contract: Launch QA found CBS ROS starting at 77-79.6 and Razzball at 79.0
(full PPR, 8 teams) against ESPN at ~70. Find out whether that is the intended
result of the method or a defect. Investigation only: no code changed, nothing
merged.

### Method
- `make sync` build of origin/main 8fbddc7 (`dist/`, build tv-20261008-0853-8fbddc7),
  served locally and loaded headless in system Chrome. 12-combo sweep
  (standard/half/full x 8/10/12/14, standard roster, default bench share).
  Each combo reads `TradeValueCurveHarness.sourceMaps()`, gets the per-position
  max for espn, cbsros, razzball, the three `*_vorp` series and the four
  published charts, and reads `TradeValueCurveDiagnostics.fixedPie` and
  `sourceScaleAgreement`. Scripts are in the session scratchpad (`peaks_sweep.py`,
  `report.py`, `report2.py`, `options.py`). They are not committed.
- The same sweep was run on a `make sync` build of 3b550db (2026-10-07 20:54).
- Options: a scratch copy of `dist/` with `adjustedMapFor` and `applyRosterShape`
  added to the harness object (one line, scratch only). It prices each leg
  before normalisation and applies the other normalisations to it.

### Verified (check named)
- **The gap is the same across the whole scale. It is not concentrated in one position.**
  (sweep, `report2.py`): in every combo, each projection series' per-position
  start divided by ESPN's is the same number at QB, RB, WR and TE, to 3 decimals.
  CBS ROS: 1.106 (half/10) to 1.163 (full/10), so every position starts 11-16%
  above ESPN in every combo. Razzball: 0.949 (full/14) to 1.072 (half/8).
  Full/8 today: ESPN QB/RB/WR/TE 27.1/69.6/41.9/29.5, CBS ROS 31.0/79.5/47.8/33.8
  (x1.143), Razzball 28.7/73.6/44.3/31.2 (x1.058).
- **Mechanism.** `rebuildDomain` sends cbsros and razzball through
  `normalizedAdjustedMapFor`. Because they have live cells, that calls
  `ValueModel.shapeToAnchorPeaksThenSharedTotal`, which does two things.
  (1) It scales each position so its peak equals ESPN's peak on the shared
  players. (2) It applies one global factor so the shared-player total equals
  ESPN's. Step 2 is the only one that moves the starts off ESPN's, and it
  moves every position by the same factor. In every combo, the
  `anchorPeakShared` value equals ESPN's plotted start, so the top player is
  always shared. CBS ROS's factor is above 1 because after step 1 its RB (and
  WR) curves fall away from the peak faster than ESPN's, which leaves less
  total. Example, standard/12, final shared totals CBS ROS vs ESPN: QB 377 vs
  231, RB 1389 vs 1490, WR 832 vs 883, TE 186 vs 180. CBS ROS's flatter QB
  depth also gets the RB-driven lift, so its QB start goes from 40.2 to 46.0.
- **Fixed pie is correct as implemented.** `fixedPieIndexed` is true in all 12
  combos. cbsros and razzball use basis `shared` (118-207 shared players), with a
  delta of 0.0 against ESPN's shared total. Per-position totals do NOT equal the
  anchor's (see above), and no code requires that. The pie is a total-only
  target. No wrong pie target, no missing rescale, and the 8-team QB step-up
  (26d01ac) does not change the shared-set pricing.
  `sourceScaleAgreement` is false in 11 of 12 combos. It is non-blocking and
  covers only the direct charts.
- **Recent merges moved Razzball, not CBS ROS** (3b550db vs 8fbddc7 sweep).
  CBS ROS factors are within about 0.01 (full/8 RB 79.5 both days). Razzball
  full/8 went from 79.6 to 73.6 (factor 1.144 to 1.058), and half/8 from 82.2 to
  75.0. Its pool changed (RB 126 to 124, TE 120 to 115 players) with the Week-5
  Razzball refresh (67e866c) and suffix resolution (de8d03b). Launch QA's
  Razzball 79.0 was the earlier pool. Because the factor is a shape statistic,
  any change to a source's projections moves all of that source's starts together.
- **The published charts are not independent evidence on starts.** USA Today,
  FantasyCalc, FantasyPros and CBS have identical per-position starts in every
  combo (12 teams: QB 25.0, RB 70.0, WR 55.0, TE 30.0), while their totals differ
  by up to 1.6x. Their starts are pinned to a fixed per-position index. The
  CLAUDE.md line about "published charts' 75-80" RB peaks is stale for the
  current build.
- **What each option would show** (`options.py`, starts QB/RB/WR/TE, ESPN in brackets):

  | combo | source | A current (peak pin + total) | B per-position pie | C total pie, no pin |
  | --- | --- | --- | --- | --- |
  | full/8 [27.1/69.6/41.9/29.5] | CBS ROS | 31.0/79.5/47.8/33.8 | 32.1/74.5/52.0/31.6 | 47.6/71.2/51.0/32.2 |
  | full/8 | Razzball | 28.7/73.6/44.3/31.2 | 41.1/66.3/50.7/24.9 | 27.8/69.4/49.5/27.1 |
  | full/12 [29.5/70.0/47.8/29.2] | CBS ROS | 33.3/79.0/54.0/33.0 | 20.6/86.9/54.6/31.1 | 24.6/84.6/54.6/30.7 |
  | full/12 | Razzball | 28.7/68.1/46.5/28.4 | 39.5/60.3/52.0/25.5 | 41.3/61.6/51.0/24.2 |
  | std/12 [40.2/70.0/43.1/23.9] | CBS ROS | 46.0/80.1/49.2/27.4 | 28.1/85.9/52.2/26.5 | 33.0/79.4/57.8/23.4 |
  | std/12 | Razzball | 41.2/71.8/44.2/24.5 | 53.8/71.0/42.6/23.8 | 55.1/73.1/41.6/20.1 |

  The full 12-combo table is in the scratchpad `options.json` output.
  The current peak pin hides large positional disagreements in the legs:
  Razzball's QB is 3-60% above ESPN's in its own leg (above 30% in 8 of 12 combos), and CBS ROS's QB is
  up to 31% below ESPN's at 12-14 teams. It also hides an 8-team CBS ROS QB
  jump. The leg's own QB peak is 46.8-59.8 at 8 teams against 20-36 at 10-14
  teams, which looks like the bench-share step-up fallback (GAP-CBSROS-8T-NO-QB).

### Claimed, not confirmed
- The peak pin was designed for the `*_adjusted` family. Its comment says it
  stops per-cell fits from pushing one position out of shape. The projection
  legs reached it because `normalizedAdjustedMapFor` is "key-agnostic". I found
  no decision record saying the projection legs should take ESPN's positional
  peaks. That conflicts with methodology.md "There is no cap at the anchor's top
  value", but I did not search decisions.md exhaustively.
- The cbsros and razzball maps hold far more players than ESPN prices (for
  example cbsros TE 94, razzball WR 186, at every team count). Those players sit
  outside the shared pie basis. I did not trace why the count is constant
  across team counts.
- I did not check the bench-share slider or custom rosters. Every number above
  is at the default share and standard roster.

### Assessment and recommendation
No defect in the pie arithmetic. The starts above ESPN follow directly from
`shapeToAnchorPeaksThenSharedTotal`. That rule is a methodology choice nobody
has signed off for projection sources, so the question goes to Jeremy:
- **A. No change.** Projection series always copy ESPN's positional
  proportions. They differ only in overall level, by a uniform 0.95-1.16x set by
  the depth shape (mostly RB). Low risk, little information.
- **B. Per-position fixed pie on the source's own leg** (scale each position's
  shared total to ESPN's for that position, no peak pin). Starts then show
  within-position steepness. CBS ROS RB 75-90 and QB 19-43. Razzball RB 59-71
  and QB 32-60. It matches "positional totals equal the anchor's".
- **C. Total-only pie on the leg, no peak pin.** The source's own
  cross-position weighting survives, which is closest to "no cap at the anchor's
  top value". It has the widest spread, including the 8-team CBS ROS QB artifact
  (47-62), which would need GAP-CBSROS-8T-NO-QB resolved first.
Under B or C the change is one line in `normalizedAdjustedMapFor`: route
cbsros and razzball to the chosen normaliser instead of
`shapeToAnchorPeaksThenSharedTotal`. The CLAUDE.md 12-combo sweep and a guard
negative test would need re-running.
