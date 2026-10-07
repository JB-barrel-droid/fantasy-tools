# 2026-10-07 - JEG-432 R2 review: feasible bench bounds (`feasible-bench/1`), merge + PR

Contract: branch `jeg432-r2-feasible-bench-bounds` (head 9a23e59) was committed
with no PR. Merge `origin/main` (merge commit), review the bounds math and edge
cases, negative-test every guard, run the 12-combo sweep against main, open the
PR. Do not merge. The original implementation entry is in `docs/claude-log.md`
("2026-10-07 - JEG-432 R2"); this entry is the review of it.

### Verified (check named)
- Merge: `git merge origin/main` (5 commits, incl. #392 JEG-436). Only conflict
  was `docs/claude-log.md` (both sides prepended entries); resolved by keeping
  both, main's JEG-436 entry first. Main does not touch `value-model.js` or
  `curve-widget.js`.
- Math (read against `TwoTier.solveTierPrices`): p_b = pie(s(bB+bS) - bB)/det
  and p_s - p_b = pie((aB+bB) - sT)/det, so the per-position feasible set is the
  open interval the rule computes; the sign handling of `gtB`/`ltE` is right
  for det < 0 and for negative denominators; pie cancels. Bench-slot test
  `rostered >= n` matches `waiverAt` (rostered == pool size -> the last player
  becomes the waiver line). `apportionSlots` is sequential highest-quotient, so
  bench allocation is monotone in the bench size; the contiguous-run rule is
  conservative if VORP-weighted flex ever made feasibility non-monotone.
- Gap found and guarded: above a position's upper edge the live slider relies
  on `calibratePositionFeasible` bisecting [0.01, requested]; that only works if
  a midpoint lands inside the position's interval, which is data-dependent.
  New guard `test_no_slider_step_withholds_a_position`
  (`tests/test_feasible_bench_bounds_parity.py`): every 0.001 step in
  [min, max], all 12 combos, all four positions, the browser's own calibration
  withholds nothing (1,819 steps; passes). Negative: rounding the min outward
  (`shareCeil` -> `shareFloor`, JS only) fails it with
  `{'standard/8': ['0.059:QB'], ...} != {}`; the in-test mutation (lower edge
  dropped, the pre-R2 0.01 floor) finds withheld steps in all 12 combos.
- Negative tests of the existing guards (each mutation applied to the real
  file, test run, file restored, test re-run green):
  - parity: JS `gtB` sign flipped -> `test_js_matches_python_reference` FAILED
    (`standard/8t/std [given]: .reasons[1] ...`).
  - pinned table: `BENCH_SLOTS_UI_MAX` 14 -> 12 in JS AND Python -> parity stays
    OK, `test_pinned_default_bounds` FAILED (`(0, 12) != (0, 14)`).
  - old floor: Python lower edge dropped -> `test_old_fixed_range_withholds`
    FAILED (`['QB', 'RB', 'WR', 'TE'] != []`).
  - closed form vs bisection: tB = bB/bS in JS AND Python -> parity OK,
    `test_closed_form_matches_bisection` FAILED (`0.0037 not less than 0.0002 :
    standard/8t/std QB lo`).
  - rendered harness on a dist copy with both league-change
    `clampBenchSlotsToFeasible()` calls removed -> rc=1,
    `slots-league: after 14 teams bench=13 shown=13, rule max 10`; on the
    pre-R2 fixed ranges -> rc=1 with share-bounds, share-clamp (withheld
    QB,RB,WR,TE at 0.01), slots-bounds, slots-clamp, slots-league. Real dist ->
    rc=0, all five checks present.
- 12-combo headless sweep (3 scorings x 8/10/12/14, Playwright on built dist/
  vs `git archive origin/main dist`): fixedPieIndexed true 12/12 both;
  sourceScaleAgreement false 12/12 both (non-blocking, unchanged); 5 curves
  everywhere; 0 page errors; per-source per-position curve starts and a digest
  of every source map's values identical in all 12 (e.g. half-PPR 12 ESPN QB
  28.12 / RB 69.98 / WR 42.62 / TE 20.94). Only the controls change: slider
  0.01-0.30 -> rule bounds (e.g. half-PPR 12 0.053-0.205); bench stepper
  0-14 -> 0-14 / 0-14 / 0-13 / 0-10 by team count. At the slider min and max in
  every combo: fixedPieIndexed true, no position withheld.
- Bench-slot bounds for custom rosters (Python reference, half-PPR): ESPN pool
  sizes QB 37 / RB 84 / WR 143 / TE 84. 12-team 2QB 0-8, 14-team 2QB 0-4,
  14-team superflex 0-10, 5-slot QB shapes: no feasible size (null).
- `make sync && make validate` exit 0 under Python 3.12 (CI's version). Stamp
  files reverted before commit.

### Claimed, not confirmed
- Environment: `/opt/homebrew/bin/chromium` on this machine is a broken cask
  wrapper (`/Applications/Chromium.app` missing), so every rendered test fails
  to launch with it; the runs above used
  `CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`.
  CI uses its own Playwright Chromium and was not observed for this branch yet.
- The share bounds use the reference-shape two-tier pool, so they do not move
  with superflex/2QB rosters; whether they should is a methodology call
  (GAP-JEG432-R2-MATH-REVIEW), not checked against any outside chart.
- Real 2QB/superflex leagues use benches deeper than 4-8 at 12-14 teams; the
  cap comes from the 37-QB projection pool, not from league practice. Not
  verified against league data.

## 2026-10-07 - JEG-432 R2: Jeremy's decisions on PR #397 (feasible-bench-001/002)

Contract: implement Jeremy's four decisions. (1) The slider ceiling stays as is.
(2) Keep the quarterback depth cap and record a row for deepening the pool.
(3) With no feasible bench size, disable the Bench stepper and show a plain
reason. (4) Compute bench-share bounds from the user's roster shape in the
browser. Merge origin/main first, record the decisions, re-run the sweep and
the negative tests.

### Verified (check named)
- Merged origin/main (incl. #394 per-PR logs, #395, #391) cleanly.
- (3): the rule (JS and Python) returns `benchSlotsBlocked` {pos, rostered,
  pool, bench}. The chart disables the stepper, leaves it blank, ignores
  input, and shows one line. Observed in the harness at 5 quarterbacks and 12
  teams: "Bench unavailable: these lineups start 60 quarterbacks across 12
  teams, but only 37 have projections, so no bench size leaves a player on
  waivers." It re-enables with "6" after going back to 1 quarterback. The
  stepper tooltip now uses plain words, with no position codes.
- Guard `slots-blocked` (harness), rc=0 on the real dist. Negative tests:
  - Dist copy with the old fail-open (`out = rule.benchSlots;`): rc=1 with
    "rule not blocked", "stepper not disabled", "disabled stepper shows a
    number: \"6\"", "reason line missing", and "typing ... moved bench 6 -> 3".
    Encoded as `test_harness_catches_fail_open_stepper`.
  - Reason line using position codes: rc=1, "reason line missing or not
    plain words: \"... start 60 QB ...\"".
- Parity: `benchSlotsBlocked` is compared exactly in all 92 vectors. Thin
  vector pinned to {QB, 12, 10, 0}.
- (4) not implemented; see decision feasible-bench-002 and
  GAP-JEG432-ROSTER-SHARE-BOUNDS.
  - The slider calibrates the reference-roster two-tier pool. Bounds from a
    user-roster pool (prototype on the same rule, half-PPR) describe a
    different calibration:
    - 12 teams superflex: 0.117-0.25 vs 0.053-0.205;
    - 12 teams bench 3: 0.016-0.088;
    - 12 teams bench 10: 0.201-0.30;
    - 14 teams bench 10 and bench 0: no feasible share.
  - No bounds are saved per roster on the backend
    (`git grep bench_share_min`: only the one-row `public.product_options`).
- New finding: CBS ROS and Razzball calibrate on their own pools with the same
  slider, and they still withhold positions near the new floor in all 12
  combos. Browser sweep at every 0.001 step calling
  `ddfTwoTierValuesFor`:
  - 6-81 withheld steps per combo;
  - e.g. half-PPR 12: Razzball WR/TE at 0.053-0.077;
  - 8 teams: CBS ROS QB at 0.060-0.126.
  Recorded as GAP-BENCH-SHARE-OTHER-POOLS. The old 0.01 floor was worse.
- 12-combo sweep, built dist vs `origin/main` dist:
  - fixedPieIndexed true 12/12 on both;
  - sourceScaleAgreement false 12/12 on both;
  - 5 curves;
  - curve starts and value digests identical;
  - at the slider min and max: fixedPieIndexed true and nothing withheld
    (ESPN);
  - 0 page errors.
- `tests.test_decisions_log` OK with feasible-bench-001 (proceeded) and -002
  (pending). `make sync && make validate` exit 0 (Python 3.12, Google Chrome).
- Risk register:
  - GAP-ESPN-QB-POOL-DEPTH, GAP-BENCH-SHARE-OTHER-POOLS and
    GAP-JEG432-ROSTER-SHARE-BOUNDS added;
  - GAP-JEG432-R2-MATH-REVIEW updated to "Partly decided".

### Claimed, not confirmed
- The disabled stepper's look (CSS) was not checked in a screenshot. Only DOM
  state was asserted.
- Option 1 in feasible-bench-002 (pool follows the roster) was not prototyped
  for values, only for bounds.
