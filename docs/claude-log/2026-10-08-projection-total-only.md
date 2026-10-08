## 2026-10-08 - Projection sources matched to the anchor by total only (GAP-PROJ-PEAK-PIN, option C)

Contract: implement Jeremy's choice of option C from
`investigate/proj-peaks`. CBS ROS and Razzball are matched to the ESPN anchor
by one factor on the shared total, with no per-position peak pin. The
`*_adjusted` series and ESPN stay as they are. First check whether the 8-team
CBS ROS QB start (47-62 in the investigation) is an artifact of the bench-share
step-up. Branch `fix/projection-total-only`, not merged.

### Change
- `app/trade-value-chart/assets/curve-widget.js` `normalizedAdjustedMapFor`:
  keys in `PROJECTION_TOTAL_ONLY_KEYS` (`cbsros`, `razzball`) return
  `ValueModel.scaleToSharedTotal(...)`. That function already scales the
  raw `*_vorp` series and has Python parity vectors. Everything else follows
  the old path (live cells go to `shapeToAnchorPeaksThenSharedTotal`;
  otherwise `normalizeTradeChartToFixedPie`).
- `tests/test_projection_total_only.py`, added to `make test-core`.
- `docs/methodology.md`: one rule paragraph under "The Three Views".
- `docs/risk-register.md`: GAP-PROJ-PEAK-PIN (fixed on branch) and
  GAP-STEPUP-EDGE-PB0 (dormant).

### Verified (check named)
- **The routing test catches the bug in both directions.** It runs the widget's
  real `normalizedAdjustedMapFor`, extracted from the file, against the real
  ValueModel on a synthetic pool. It passes on the branch (3/3). Against origin/main's
  curve-widget.js it fails `test_projection_sources_keep_their_own_positional_weighting`
  (cbsros per-position factors QB 0.61 / RB 2.03 / WR 1.22, which is the peak pin).
  Against a mutant that routes every key total-only it fails
  `test_adjusted_series_keep_the_peak_pin` (fantasycalc_adjusted QB 2.41 / RB 0.72).
- **The 12-combo sweep** (headless system Chrome, `make sync` builds of the
  branch and of origin/main b45bdff, `/classic/`, standard roster, default
  share; script `projc/sweep.py` in the session scratchpad). Only `cbsros` and
  `razzball` change, at every position and combo. espn, the three `*_vorp`, the
  four published charts and the four `*_adjusted` series are identical.
  `fixedPieIndexed` is true in all 12 combos on both builds. The cbsros and
  razzball total over players shared with ESPN equals ESPN's to within 1e-4 in
  every combo. `sourceScaleAgreement` is the same on both builds (true only at
  ppr/12; non-blocking, covers the direct charts).

  Per-position starts, QB/RB/WR/TE:

  | combo | ESPN | CBS ROS main | CBS ROS branch | Razzball main | Razzball branch |
  |---|---|---|---|---|---|
  | standard/8 | 36.5/69.9/42.3/23.4 | 39.2/75.1/45.5/25.1 | 45.5/71.5/45.4/29.8 | 37.9/72.7/44.0/24.3 | 41.1/67.8/50.1/22.4 |
  | standard/10 | 33.3/70.0/43.3/24.5 | 36.8/77.2/47.8/27.1 | 31.9/76.5/52.0/23.4 | 34.8/73.1/45.2/25.6 | 42.3/72.0/47.4/19.4 |
  | standard/12 | 40.2/70.0/43.1/23.9 | 44.6/77.6/47.7/26.5 | 37.0/77.1/53.0/23.3 | 41.2/71.8/44.2/24.5 | 55.1/73.1/41.6/20.1 |
  | standard/14 | 45.1/69.7/41.9/19.4 | 51.0/78.7/47.3/21.9 | 44.3/85.6/43.7/23.6 | 45.9/70.9/42.6/19.8 | 59.9/65.6/44.4/21.7 |
  | half/8 | 34.7/70.0/47.2/28.2 | 39.0/78.6/53.0/31.7 | 43.1/80.2/51.1/29.6 | 37.2/75.0/50.6/30.2 | 36.3/68.4/59.6/27.4 |
  | half/10 | 26.3/69.7/39.9/26.3 | 28.3/75.1/43.0/28.3 | 26.5/67.9/51.8/23.9 | 26.3/69.7/39.9/26.3 | 33.8/62.7/48.4/20.1 |
  | half/12 | 36.7/70.0/47.4/26.0 | 42.8/81.6/55.3/30.3 | 33.4/90.0/54.8/25.5 | 38.4/73.3/49.6/27.2 | 50.2/69.7/51.8/23.6 |
  | half/14 | 37.7/69.5/40.5/26.6 | 42.5/78.3/45.7/30.0 | 38.8/80.2/45.9/29.4 | 37.1/68.3/39.8/26.1 | 50.4/62.6/43.4/22.9 |
  | ppr/8 | 27.1/69.6/41.9/29.5 | 28.7/73.7/44.4/31.3 | 35.8/64.0/50.5/29.7 | 28.7/73.6/44.3/31.2 | 27.8/69.4/49.5/27.1 |
  | ppr/10 | 22.3/69.7/41.8/31.6 | 24.5/76.4/45.8/34.6 | 23.1/71.7/51.2/28.2 | 21.5/67.1/40.3/30.4 | 29.3/57.2/51.5/22.0 |
  | ppr/12 | 29.5/70.0/47.8/29.2 | 32.8/77.9/53.2/32.5 | 27.6/82.1/53.6/29.3 | 28.7/68.1/46.5/28.4 | 41.3/61.6/51.0/24.2 |
  | ppr/14 | 31.9/70.0/41.1/29.0 | 35.8/78.4/46.0/32.5 | 33.6/79.9/46.7/30.7 | 30.3/66.4/39.0/27.5 | 43.4/59.9/43.4/22.1 |

  On main, each CBS ROS / Razzball row is ESPN's row times one number. On the
  branch, each is the source's own leg times one number. For example, the
  ppr/8 CBS ROS leg on its own 70 scale is 39.1/70/55.3/32.5, and every
  position is about x0.915 of that.
- **The 8-team CBS ROS QB is not a step-up artifact on today's data. The step-up
  does not fire at all.** Node script `projc/qb8.js` (scratchpad) runs the
  browser's `TwoTier` pricing (buildPositionTiers, calibratePositionFeasible at
  0.15, priceForProjection, 70/max) on players.json for espn, cbsros and
  razzball across the 12 combos. With the current players.json (a6a4960, a
  fresh CBS ROS pull) every source and combo calibrates at 0.15 directly. The
  8-team CBS ROS QB has pb 0.46 and ps 2.39, and the leg QB start is
  39.1/37.6/44.5 (ppr/half/std). On the branch that becomes 35.8/43.1/45.5,
  against ESPN's 27.1/34.7/36.5. The gap is genuine: CBS ROS gives QBs more
  surplus over the waiver QB than ESPN does relative to RBs. At ppr/8 the CBS
  ROS QB pie is 42.2 against an RB pie of 187.8 (0.22). ESPN's is 28.9 against
  231.1 (0.13). The top QB's share of its own QB pie is similar, 0.22 for CBS
  ROS and 0.28 for ESPN.
- **On the investigation's pool (8fbddc7 players.json) the step-up did fire.**
  It contributed to the 47-62, but did not cause it alone. Same script: the
  8-team CBS ROS QB stepped up to share 0.1602 with pb = 0.0000 (the window's
  lower edge) and ps 4.76. Allen (25.1 ppg against QB2 22.9) took 30.6% of the
  QB pie, which gave leg starts of 46.8/53.0/59.8. Holding the pool fixed, his
  share would be 30.0% at 0.165, 28.1% at 0.18 and 19.7% at 0.25. So landing
  on the edge adds a little. Most of the high start comes from the pool: a big
  QB pie relative to RB, plus one clear outlier. The pool changed for 348
  players between the two builds. The QB tier is less flat now (QB2-QB8
  23.5-22.4, was 22.9-22.5), so 0.15 is feasible. Logged as GAP-STEPUP-EDGE-PB0
  (dormant). I did not change it: it is the JEG-74 "nearest feasible share"
  rule, shared with the Python leg builders, and today it changes no value.
- **No server-side normaliser needed a mirror.** A grep for
  `shape_to_anchor_peaks` / `scale_to_shared_total` / `shapeToAnchorPeaks` /
  `sharedPieBasis` outside the widget finds only the ValueModel parity mirror
  (`pipelines/parity/value_model_parity.py`, `check_valuemodel_parity.py`). It
  mirrors the primitives, not the routing. The cbsros and razzball fixture
  sections are stored on the leg's own 70/max scale and anchored only in the
  browser. `tests/cbsros_live_section_harness.js` compares those pre-anchor
  values, and `test_cbsros_8t_qb`, `test_razzball_refresh` and
  `test_suffix_identity` pass under `make validate`.
- **`make sync` and `CHROMIUM_PATH=<system Chrome> make validate` exit 0** on the
  branch. Build churn was reverted with `git checkout --`.

### Claimed, not confirmed
- The history accessor (`getWeekValues` → `historyProjectionValues`) and v2
  inherit the rule because both go through `normalizedAdjustedMapFor` /
  `sourceMaps`. I confirmed this by reading the code, not by running them.
- Only the default bench share and the standard roster were swept. I did not
  check the bench-share slider or custom rosters.
- The CLAUDE.md note about "published charts' 75-80" RB peaks is still stale
  (all four charts start at RB 70.0). Left for Jeremy, not edited here.
