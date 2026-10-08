## 2026-10-07 - GAP-025: ESPN-0 players are worth 0.0, not missing

Contract: implement Jeremy's decision ("Yes, use 0"): when ESPN lists a player
but projects 0 (injured/out), our ESPN value is 0.0, so a chart that still pays
for him is a sell target with a real gap. Keep the badge. Players with no ESPN
row stay missing (—). Do not move any other series. Branch
`fix/espn-zero-value`, not merged.

### What changed
- `curve-widget.js`: `rowValue(key, player)` builds each row's values. For
  `espn` and `espn_vorp`, a player with `espnProjectsZero` who is not in the map
  gets 0 (only when the series has data at this setting). The zero is added to
  the row, never to `sourceMaps`, so the anchor every chart is indexed against,
  its pie, peaks and the diagnostics cannot move.
- `comparison-dashboard.js`: the same rule in `sourceValue` (main table).
- `app/v2/targets.js`, `v2.js`, `shell.html`, `v2.css`: the separate "ESPN
  projects 0, but a chart still pays" list is retired. It listed the same
  players with the same chart values and no gap; they are now ordinary sell
  rows (badge kept, our value 0.0, gap = chart value), so it added nothing.
- `product-data.js`: badge tooltip says our ESPN value is 0.0.
- `docs/methodology.md`: one rule line. `docs/risk-register.md`: GAP-025
  updated; new row GAP-ESPN-BELOW-LEG.
- CBS ROS / Razzball: no change needed. They have no "ineligible" status; a
  row projecting 0 in every scoring (4 backup QBs in CBS ROS) is already priced
  0 by their legs, and a player with no row (e.g. Achane, no CBS ROS row) is
  missing, which is right.

### Verified (check named)
- 12-combo headless sweep (system Chrome; ppr/half_ppr/standard x 8/10/12/14),
  `make sync` build of origin/main (ddc722a) vs the branch's `make sync` build,
  script reading `TradeValueCurveDiagnostics`, every `sourceMaps()` map and
  full `getRows()`:
  - `fixedPieIndexed`, `fixedPie`, `sourceScaleAgreement`, `scaleAgreement`,
    `sourcePeaks`: identical in all 12 combos (fixedPieIndexed true;
    sourceScaleAgreement false on both, the known GAP-026).
  - every source map (all 14 series): identical in all 12 combos.
  - `getRows()`: same 515 players; the only value changes are 272 cells per
    combo, the 136 ESPN-0 players' `espn` and `espn_vorp`, null to 0. No other
    cell or field changed. Row order changes only in that those 136 rows now
    sort among the ESPN-priced rows' zero end instead of the missing tail;
    the relative order of all other rows, and of the 136 among themselves, is
    unchanged.
  - ESPN-0 players a published chart pays for: Coleman (FantasyPros 13.6) and
    Stribling (USA Today 0.8) at 12 teams; at 14 teams also Jonathon Brooks
    (USA Today 2.8) and Tank Dell (FantasyCalc 0.1); none at 8 teams.
- `tests/test_espn_zero_badge_render.py` (rewritten for the 0.0 rule): every
  ESPN-0 row has espn = espn_vorp = 0; every no-ESPN-row player has espn null;
  main table ESPN column 0.0 for Stribling and — for Bauer Sharp; v2 Trade
  targets sell list (ESPN as our value) holds every paid ESPN-0 player with
  ours 0 and gap = chart value, rendered row shows 0.0, the badge and +gap; no
  no-ESPN-row player in it; retired list gone. Passes. Against origin/main's
  curve-widget.js, comparison-dashboard.js and targets.js: 5 errors. Mutation
  subtests (engine rule removed, table rule removed, badge flag removed,
  absent read as 0) each fail the checks.
- `CHROMIUM_PATH=... make validate`: exit 0. Also passing:
  test_v2_targets, test_v2_targets_render, test_build_v2_page,
  test_published_views_render, test_published_league_settings_render,
  test_disagreement_units_render, test_espn_zeroed_staleness.

### Claimed, not confirmed
- The main chart's ESPN line now drops to 0 at an ESPN-0 player's rank when
  the chart is locked to another source; read from the code (the line draws
  `row.values`), not looked at.
- Players ESPN projects above 0 but below the built leg's waiver line still
  show — on ESPN (15-20 per combo with a positive chart value). Counted in the
  sweep; whether they should be 0.0 too is a decision (GAP-ESPN-BELOW-LEG).
