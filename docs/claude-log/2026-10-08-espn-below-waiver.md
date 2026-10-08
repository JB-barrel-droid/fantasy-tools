## 2026-10-08 - GAP-ESPN-BELOW-LEG: below-leg players are worth 0.0, not missing

Contract: Jeremy (2026-10-07): a healthy player ESPN projects above 0 but below
its waiver line counts as 0.0 for our value, display only like the injured case
(GAP-025); the anchor/pie must not move; no ESPN row stays —. Apply the same to
CBS ROS / Razzball if they show the same behaviour. Branch
`fix/espn-below-waiver` from origin/main 3b550db, not merged.

### What changed
- `curve-widget.js` `rowValue`: on espn / cbsros / razzball, a player missing
  from the leg gets 0 when his per-game projection (espn_ppg / cbsros_ppg /
  rz_ppg at the current scoring) is at or below the lowest projection the leg
  prices at his position (`buildLegFloors`, recomputed each rebuildDomain).
  Above that line, or at a position the leg prices no one, he stays missing.
  Rows only; sourceMaps untouched. The GAP-025 ESPN-0 rule is unchanged.
- `*_vorp` series: no change; they already price every projected player (0 at
  or below waivers): the sweep found 0 projected-but-missing cells on them.
- CBS ROS / Razzball legs: Razzball has no projected-but-missing cells in any
  combo; CBS ROS has none at 10/12/14 teams. At 8 teams CBS ROS prices no QB
  at all (63 QBs incl. Josh Allen): that is a leg defect, not "below the
  line", so the floor rule leaves them — (new GAP-CBSROS-8T-NO-QB).
- Main comparison table: no change. Its ESPN column reads the built fixture
  leg, which already shows 0.0 for these players (299 zeros, 35 —, same on
  both builds). A dashboard copy of the rule was written, measured as a no-op,
  and removed.
- `tests/test_espn_zero_badge_render.py`: mutation anchor updated to the new
  `rowValue` line (the assertion itself is unchanged).

### Verified (check named)
- 12-combo headless sweep (system Chrome), `make sync` builds of origin/main
  3b550db vs this branch, reading TradeValueCurveDiagnostics, every source map
  and full getRows():
  - fixedPieIndexed, fixedPie, sourceScaleAgreement, scaleAgreement,
    sourcePeaks: identical in all 12.
  - all 14 source maps: identical in all 12.
  - getRows(): same players; only changes are ESPN null to 0: 221 / 192 / 163
    / 132 cells at 8 / 10 / 12 / 14 teams (each scoring); no other cell or
    field; rows whose values did not change keep their relative order. Of the
    newly-zero players, 14-21 per combo have a positive published value.
  - Before the change, every ESPN projected-but-missing player sat strictly
    below the lowest priced projection at his position (checked per combo),
    so the floor rule zeroes all of them and leaves none above the line.
  - At 12-team PPR the built fixture ESPN leg (getPlayerValues view
    combo_reindexed) itself has 0 for all of these players but Najee Harris
    (0.5); Waller is 0 there.
- `tests/test_below_leg_zero_render.py` (new): at 12- and 8-team PPR every
  espn/cbsros/razzball cell matches an expectation computed in Python from the
  raw maps and #players-data; CBS ROS QBs at 8 teams stay —; Darren Waller has
  engine ESPN 0 and is a v2 Trade targets sell row with ours 0.0 and gap =
  chart value (USA Today 1.1, FantasyCalc 1.5), rendered "0.0". Passes. On
  origin/main's curve-widget.js: 4 errors. Mutations (rule removed; no floor)
  both caught.
- `CHROMIUM_PATH=... make validate`: exit 0. Also passing:
  test_espn_zero_badge_render, test_v2_targets, test_v2_targets_render,
  test_build_v2_page, test_published_views_render,
  test_published_league_settings_render, test_disagreement_units_render,
  test_espn_zeroed_staleness.

### Found, not fixed (risk register)
- GAP-CBSROS-8T-NO-QB: CBS ROS · DDA prices no QB at 8 teams.
- GAP-MAIN-TABLE-ESPN-DRIFT: the main comparison table shows Waller ESPN 3.4
  while the engine and the built leg have 0; and its _adjusted columns vary
  between identical loads of the origin/main build (FC Adjusted 2.0 vs 4.8).

### Claimed, not confirmed
- The chart's ESPN line now draws these players at 0 (it plots row values);
  not looked at.
- Why ESPN raw VORP (Waller 3.7) and ESPN · DDA (0.0) use different waiver
  lines was not investigated; it predates this change.
