# QB values on a 2-QB board, and the part-timer per-game question (JEG-702)

2026-10-16. Investigation only: no value math was changed. Follows
`docs/decisions.md` jeremy-review-2026-10-16 item 5 ("KEEP loosened, then have
QB values reviewed") and `docs/math-review-agenda.md` MR-20 / JEG-535.

**Inputs.** `origin/main` at `bd80477a`. `data/fixtures/current/players.json`
as of 2026-10-16 (ESPN snapshot 2026-10-15, ROS weeks 6-18) and
`comparison-sources-data.json` at the same commit. Unless a table says
otherwise: PPR, 12 teams, bench 7, FLEX 1. "1-QB" is the default roster;
"2-QB" sets the QB stepper to 2 (the page allows 1 to 5); "SF" is the default
roster plus one SUPERFLEX slot.

**How the numbers were made.** All engine numbers come from the Python
reference `pipelines/value_reference.py` (`Setting`, with `league.slots["QB"]`
set to 2 for the 2-QB rows). The cap counterfactuals edit ESPN's per-game
input in memory only. Translation numbers come from
`pipelines/vorp_translation/unified.py`. The scratch scripts are not
committed; each table names the function it reads.

## 1. Which "32"?

The number in the ticket (the 2-QB QB max fell from about 60 to about 32; 1-QB
is 25) is `positional_max_for_setup()["QB"]` in
`pipelines/vorp_translation/unified.py`, the as-published translation's
league-following max. It is the quantity checked by
`tests/test_vorp_translation_js_parity.py::direction_problems` (+3 over 25)
and `test_translation_onto_derived_maxes_js_equals_python` (peak > 28).

**That path does not price anything on the page.** Verified by grep: no code
under `app/` calls `positionalMaxForSetup` or `translatePublishedVorp`
outside `value-model.js` itself. Only the parity test driver
(`tests/vorp_translation_parity_driver.js`) calls them.
`pipelines/rebuild_comparison_chain.py` says the translation grains "are a
record only since JEG-482: no saved chart value is read from them", and
`refresh_vorp_translation.py` only runs the 12-team default. When a reader
sets QB = 2, the value comes from the source-neutral pipeline (VP-0 to VP-12),
the same math as `value_reference.py`. Section 3 reviews that board.

### 1a. Why the translation max moved (verified on fixture history)

`projection_max_vorp` measures the top ESPN QB rate minus the waiver QB's rate.
The 2-QB max is `25 x M(2-QB) / M(1-QB)`, then all positions are rescaled so
the top one is 70.

| players.json (ESPN snapshot) | ESPN basis | QBs with an ESPN rate | M 1-QB (waiver QB) | M 2-QB (waiver QB) | 2-QB QB max |
|---|---|---|---|---|---|
| 2026-10-10 (10-10) | per team game | 35 | 8.58 | 22.66 | 66.0 |
| 2026-10-12 (10-12) | per team game | 35 | 9.16 | 22.63 (Jalon Daniels, 1.30) | 61.8 |
| CI, PR 637 (week 6) | per game played | not seen | not seen | not seen | 32.3 (from the PR body, not reproduced) |
| 2026-10-16 (10-15), current | per game played | 36 | 8.90 (Tanner McKee, 16.18) | 14.02 (J.J. McCarthy, 11.06) | 39.4 |

The translation's 2-QB roster holds 38 QBs (`rostered_for_teams`), but ESPN
rates only 35 or 36. So the 2-QB "waiver line" is not a waiver line at all:
it is the last QB on ESPN's list (`rows[-1]`). Before JEG-535 that was a
1-game backup at 1.30 points per team game, which made M(2-QB) large (60+).
Now it is McCarthy at 11.06 per game played. The 1-QB line is set by McKee,
who ESPN projects for **1 game** at 16.18. Both endpoints are part-timer
artifacts. The swing from 62 to 32 to 39 is mostly about which backup sits
at the bottom of ESPN's list, not about how scarce QBs are.

## 2. Who the part-timers are (verified)

These are ESPN rows where `espn_expected_games` (ROS weeks with any projected
stat) is below the team's `games_remaining`. The per-team-game rate is
`espn_ros / games_remaining`, the pre-JEG-535 basis.

| QB | Team | ESPN games / team games | Per game played (now) | Per team game | CBS ROS ppg | Razzball ppg |
|---|---|---|---|---|---|---|
| Fernando Mendoza | LV | 7 / 12 | 18.57 | 10.83 | 0.74 | 7.0 |
| Jalen Hurts | PHI | 11 / 12 | 17.61 | 16.14 | 19.87 | n/a |
| Jameis Winston | NYG | 5 / 12 | 17.10 | 7.12 | 11.88 | 10.1 |
| Kirk Cousins | LV | 5 / 12 | 17.09 | 7.12 | 15.88 | n/a |
| Tanner McKee | PHI | 1 / 12 | 16.18 | 1.35 | 1.45 | n/a |
| Baker Mayfield | TB | 11 / 12 | 15.82 | 14.50 | 18.80 | 13.9 |
| Jalon Daniels | TB | 1 / 12 | 15.54 | 1.29 | 1.78 | n/a |

The part-timer issue is not QB-only. All positions:

| Position | ESPN games < team games | Below half the team games (< 6) |
|---|---|---|
| QB | 7 | 4 |
| RB | 19 | 8 (for example Roschon Johnson, 1 game at 7.49, 0.62 per team game) |
| WR | 16 | 7 (for example Ben Skowronek, 1 game at 4.78) |
| TE | 0 | 0 |

**Observation, not explained.** For backups, CBS ROS rates sit near zero
(McKee 1.45, Mendoza 0.74, McCarthy 1.5). That is how a per-team-game rate
behaves, even though MR-20 records CBS ROS as per game played. Since JEG-535,
ESPN is the only source that prices backups at starter-like rates. I did not
check how CBS computes `gp` for these rows.

## 3. The page's QB values: 1-QB vs 2-QB vs SF (reference engine, as is)

### 3a. Examples (PPR, 12 teams), Adjusted tab

DDF = blended DDF value. ESPN, CBS ROS and Razzball are each source's
Adjusted value. Rank is by DDF.

| QB | 1-QB DDF | 1-QB ESPN / CBS ROS / Razzball | 2-QB DDF | 2-QB ESPN / CBS ROS / Razzball | SF DDF | SF ESPN / CBS ROS / Razzball |
|---|---|---|---|---|---|---|
| Josh Allen (QB1) | 33.1 | 30.1 / 27.3 / 31.7 | 58.3 | 39.6 / 29.9 / 36.9 | 52.9 | 59.5 / 48.3 / 39.5 |
| Lamar Jackson | 22.4 | 13.2 / 14.6 / 15.8 | 46.3 | 25.8 / 24.7 / 27.7 | 32.9 | 31.0 / 31.4 / 28.4 |
| Drake Maye | 21.4 | 22.0 / 6.8 / 13.0 | 40.5 | 33.2 / 20.5 / 26.0 | 37.5 | 45.8 / 20.6 / 26.3 |
| Joe Burrow | 14.4 | 15.5 / 20.8 / 13.8 | 29.6 | 27.9 / 27.2 / 26.5 | 31.0 | 35.0 / 39.3 / 26.9 |
| Patrick Mahomes | 12.1 | 9.5 / 11.8 / n/a | 28.1 | 22.4 / 23.4 / n/a | 25.5 | 24.5 / 27.7 / n/a |
| Bryce Young (about QB12) | 7.1 | 9.2 / 4.1 / 9.3 | 18.7 | 22.0 / 18.4 / 23.3 | 22.7 | 24.0 / 15.9 / 23.3 |
| Matthew Stafford | 4.5 | 5.7 / 9.9 / 11.3 | 14.7 | 18.0 / 22.4 / 24.8 | 19.3 | 17.0 / 25.2 / 25.0 |
| Kyler Murray | 1.9 | 5.0 / 2.1 / 0.9 | 10.0 | 17.2 / 15.9 / 11.4 | 14.2 | 15.7 / 11.3 / 10.4 |
| Sam Darnold (about QB24) | 0.4 | 1.1 / 2.6 / 2.9 | 5.9 | 10.6 / 16.7 / 16.2 | 10.0 | 5.5 / 12.7 / 15.5 |
| Geno Smith (backup tier) | 0.0 | 0.0 / 0.3 / 0.2 | 4.7 | 7.0 / 10.7 / 7.4 | 3.7 | 1.1 / 3.5 / 6.4 |
| Cam Ward | 0.0 | 0.0 / 0.0 / 0.0 | 2.5 | 1.9 / 7.5 / 15.8 | 0.0 | 0.0 / 0.0 / 0.0 |
| Top RB (Gibbs) | 69.0 | | 68.3 | | 66.3 | |

QB share of the blended pie: 9.4% at 1-QB, 21.1% at 2-QB, 20.7% at SF.

At 2-QB the waiver QB differs by source: ESPN 11.06 (McCarthy), CBS ROS 1.45,
Razzball 1.2. The 2-QB line sits among backups, and that is exactly where
ESPN's new basis and the other two disagree.

### 3b. Every scoring and team count (blended DDF)

| Scoring | Teams | 1-QB: QB1 / QB6 / QB12 / RB1 | 2-QB: QB1 / QB6 / QB12 / QB24 / RB1 | SF: QB1 / QB12 | Translation 2-QB max |
|---|---|---|---|---|---|
| standard | 8 | 30.3 / 10.1 / 3.0 / 66.8 | 37.2 / 17.5 / 8.2 / 0.0 / 71.2 | 43.9 / 8.6 | 26.9 |
| standard | 10 | 31.5 / 13.1 / 5.0 / 70.1 | 52.8 / 24.9 / 13.7 / 1.5 / 71.6 | 50.4 / 14.9 | 30.5 |
| standard | 12 | 37.4 / 16.8 / 8.0 / 71.3 | 64.7 / 32.8 / 20.7 / 6.6 / 68.2 | 57.9 / 23.3 | 39.4 |
| standard | 14 | 49.1 / 22.6 / 11.5 / 71.2 | 76.4 / 39.6 / 25.1 / 9.1 / 68.1 | 60.6 / 35.9 | 37.4 |
| half PPR | 8 | 30.1 / 10.0 / 2.9 / 67.2 | 36.4 / 17.1 / 8.0 / 0.0 / 71.6 | 42.9 / 8.5 | 26.5 |
| half PPR | 10 | 29.5 / 12.3 / 4.6 / 68.0 | 49.3 / 23.2 / 12.8 / 1.4 / 70.0 | 47.6 / 14.1 | 30.7 |
| half PPR | 12 | 35.4 / 15.9 / 7.6 / 69.4 | 61.8 / 31.3 / 19.8 / 6.3 / 67.8 | 55.4 / 22.3 | 39.4 |
| half PPR | 14 | 46.2 / 21.3 / 10.9 / 70.1 | 72.2 / 37.4 / 23.7 / 8.6 / 68.1 | 57.9 / 34.3 | 37.0 |
| PPR | 8 | 28.2 / 9.3 / 2.7 / 65.3 | 34.2 / 16.1 / 7.6 / 0.0 / 70.0 | 40.3 / 8.0 | 26.8 |
| PPR | 10 | 27.9 / 11.6 / 4.4 / 66.3 | 46.4 / 21.9 / 12.1 / 1.3 / 68.5 | 45.0 / 13.3 | 30.7 |
| PPR | 12 | 33.1 / 14.8 / 7.1 / 69.0 | 58.3 / 29.6 / 18.7 / 5.9 / 68.3 | 52.9 / 21.3 | 39.4 |
| PPR | 14 | 44.3 / 20.4 / 10.4 / 69.0 | 69.4 / 36.0 / 22.8 / 8.3 / 68.4 | 55.5 / 32.8 | 36.8 |

The engine's 2-QB top QB is 1.21 to 1.76 times its 1-QB value. At 14 teams it
passes the top RB in all three scorings: 76.4, 72.2 and 69.4 against RB1
68.1, 68.1 and 68.4.

### 3c. Market benchmark (published charts in the fixture, PPR 12)

| List | QB1 / RB1 | QB12 / RB1 | QB24 / RB1 |
|---|---|---|---|
| FantasyCalc 1-QB | 0.56 | 0.12 | 0.03 |
| FantasyCalc superflex (`native_superflex`) | 1.04 | 0.37 | 0.12 |
| USA Today 1-QB | 0.50 | 0.19 | 0.03 |
| FantasyPros 1-QB | 0.39 | 0.07 | 0.01 |
| CBS 1-QB | 0.41 | 0.13 | n/a |
| Engine 1-QB (blended) | 0.48 | 0.10 | n/a |
| Engine 2-QB (blended) | 0.85 | 0.27 | 0.09 |
| Engine SF (blended) | 0.80 | 0.32 | n/a |
| Translation 2-QB max / 70 (as is) | 0.56 | | |

FantasyCalc is the only fixture source with a superflex list, and no source
publishes a true 2-QB list. On FantasyCalc's superflex market the engine's
2-QB board is about 18% low at the top and about 27% low at QB12.

## 4. What a part-timer cap would change (counterfactual, ESPN input only)

| Variant | ESPN per-game denominator |
|---|---|
| C0 as is | ESPN projected games (JEG-535) |
| C1 per team game | team games remaining (pre-JEG-535) for everyone |
| C2 floor | max(ESPN games, half the team games), which caps the rate at `ros / 6` |
| C3 revert below half | team games only where ESPN games < half the team games, else ESPN games |

### 4a. Headline numbers (PPR 12)

| | C0 | C1 | C2 | C3 |
|---|---|---|---|---|
| Translation 2-QB QB max | 39.4 | 57.9 | 60.4 | 63.9 |
| Translation 1-QB waiver QB | McKee 16.18 | Herbert 14.81 | Penix 15.77 | Penix 15.77 |
| 1-QB Allen DDF (ESPN Adjusted) | 33.1 (30.1) | 33.0 (28.2) | 32.9 (29.3) | 32.9 (29.3) |
| 2-QB Allen DDF (ESPN Adjusted) | 58.3 (39.6) | 61.0 (34.0) | 60.8 (34.2) | 61.1 (34.1) |
| SF Allen DDF (ESPN Adjusted) | 52.9 (59.5) | 49.5 (42.3) | 50.6 (50.3) | 50.3 (48.4) |
| 2-QB ESPN waiver QB rate | 11.06 | 1.29 | 2.59 | 1.29 |
| 2-QB QB share of blended pie | 21.1% | 23.3% | 23.2% | 23.3% |
| 2-QB top RB DDF | 68.3 | 64.5 | 66.0 | 65.9 |

### 4b. The affected QBs (2-QB, blended DDF, with the ESPN Adjusted line in brackets)

| QB | C0 | C1 | C2 | C3 |
|---|---|---|---|---|
| Fernando Mendoza | 5.6 (16.7) | 1.1 (3.3) | 6.8 (20.3) | 6.9 (20.7) |
| Kirk Cousins | 7.8 (10.7) | 5.3 (2.0) | 6.7 (6.1) | 5.3 (1.9) |
| Jameis Winston | 5.9 (10.7) | 3.3 (2.0) | 4.7 (6.1) | 3.3 (1.9) |
| Tanner McKee | 2.7 (7.4) | 0.0 (0.0) | 0.3 (0.0) | 0.0 (0.0) |
| Jalon Daniels | 2.0 (5.4) | n/a | 0.2 (0.0) | n/a |
| Jalen Hurts | 14.8 (12.8) | 16.2 (13.8) | 17.3 (17.1) | 17.5 (17.6) |
| Mid starter: Stafford | 14.7 (18.0) | 17.1 (22.5) | 16.7 (21.2) | 16.8 (21.7) |
| Late starter: Darnold | 5.9 (10.6) | 8.3 (17.0) | 7.7 (15.2) | 7.9 (15.7) |

(n/a means outside the top 45 QBs by DDF in that variant.) At 1-QB the
affected QBs move by 0.6 or less in DDF. Mendoza is the exception under C1,
where he leaves the top 45.

**Reading.** At 2-QB, as-is part-timers carry 2 to 8 points of blended value
(5 to 17 on the ESPN line) that the C1/C3 bases put near 0 to 5. Every cap
lowers ESPN's 2-QB waiver rate (11.06 to 1.3-2.6), which lifts every real
starter by 2 to 4 blended points and the late starters on the ESPN line by
4 to 6. In the engine, the cap barely moves Allen at 2-QB (58.3 to about 61).
It moves the translation max a lot (39.4 to 58-64), because there the waiver
is the bottom of ESPN's list. In SF, ESPN's own Allen falls from 59.5 to
42-50. That is the biggest single-source effect.

## 5. Other findings (no question attached)

- **SF and 2-QB disagree on the ESPN line.** As is, Allen is 59.5 at SF but
  39.6 at 2-QB. Both settings start 24 QBs, but SF rosters 30 QBs and 2-QB
  rosters 35 (`roster_convention` bench split). ESPN's SF waiver (15.69) is
  far above its 2-QB waiver (11.06). Under a cap the gap narrows (C2: 50.3
  vs 34.2) but does not close. This is worth its own ticket if Jeremy wants SF
  and 2-QB to price QBs alike.
- **Two roster conventions.** At 2-QB the translation rosters 38 QBs
  (`vorp_via_roster`) and the engine rosters 35 (`roster_convention`). JEG-556
  "one definition per step" applies only if the translation stays.
- **Chart natives at 2-QB.** With the QB stepper at 2, the published charts
  keep their 1-QB lists. Only SUPERFLEX swaps in `native_superflex`, and
  FantasyCalc's 2-QB waiver is estimated (`method: estimated`, 34 listed).

## 6. Open questions and options

**Q1. What should guard 2-QB QB value?** The +3 and >28 checks guard a
translation the page no longer uses (section 1).
- (a) Keep the checks as they are.
- (b) Re-point the direction check at the engine: the 2-QB top-QB DDF must
  exceed the 1-QB value by a stated ratio. Today the ratio runs from 1.21
  (8 teams, PPR and half PPR) to 1.76 (12 teams, PPR).
- (c) Retire the translation checks together with the dead
  `positionalMaxForSetup` / `translatePublishedVorp` path.
- (d) Do both (b) and (c).

**Q2. Is the engine's 2-QB QB level right?** At PPR 12 the top QB is 58
(0.85 of RB1) and QB12 is 19, against FantasyCalc superflex at 1.04 and 0.37.
- (a) Accept: the engine's scarcity is the product, and no publisher has a
  true 2-QB list.
- (b) Treat FantasyCalc superflex as a calibration target and review the QB
  share at SF/2-QB.
- (c) Park until a second superflex or 2-QB source is wired.

**Q3. Cap part-timers' per-game rates?**
- (a) No cap (C0). Per game played stays (MR-20 interim default). Part-timers
  keep 2 to 8 points of 2-QB value, and ESPN alone prices backups like
  starters.
- (b) Floor at half the team games (C2). It touches 4 QBs, 8 RBs and 7 WRs.
  Mendoza keeps his 7-game rate.
- (c) Per team game below half the team games (C3). It touches the same 19
  players, harder.
- (d) Per team game for all of ESPN (C1). This undoes JEG-535 for ESPN.

Any cap is a value-math change, so it needs the JS and Python reference on
one branch, `value_check compare` at 0, the rank guard at 0 and the 12-combo
sweep.

## Verified vs assumed

**Verified** (run on `bd80477a`):
- `tests.test_vorp_translation_js_parity.PositionalMaxParity`: 6 tests OK,
  JS equals Python on 432 translation vectors.
- `tests.test_value_reference_worked_example`: 16 OK.
- Every table above comes from running `value_reference.Setting` /
  `unified.positional_max_for_setup` on the committed fixtures.
- Fixture history (section 1a) comes from `git show` of each `players.json`
  revision.
- The page has no caller of the translation functions (grep of `app/`).

**Assumed, not verified:**
- That the browser engine equals the reference at **QB = 2**. `value_check`
  compares only the default and SF settings, and `make sync` was not run here,
  so no headless engine run was made.
- Runs used no week history (`dist/assets/history` is absent in a fresh
  worktree), so every eligible source is included. The live page's included
  set can be smaller.
- The 32.3 figure is from the PR 637 body (CI data).
- That FantasyCalc's superflex list is a fair benchmark for a 2-QB league
  (superflex is the looser format).
- Why CBS ROS rates backups near zero.
