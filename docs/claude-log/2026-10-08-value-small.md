## 2026-10-08 - value fixes: per-game tie flip, K/DST games, superflex read (fix/value-small)

Contract:
- GAP-PPG-TIE-FLIP: trace the 10.9-point bias-adjusted jump and fix it where it can be avoided.
- GAP-KDST-GAMES-FIXED: K/DST games from pipelines/lib/games_remaining.py.
- JEG332-SUPERFLEX-FLEX: fix it only if it is a clear bug, otherwise write up options.
- Run the 12-combo sweep against origin/main (196906f).

Branch pushed. Not merged.

### Answer in one line
The tie flip was a server/browser parity bug. The bake rounded per-game rates to 2 dp before the browser ranked on them, while the leg ranked on unrounded rates. Fixed by publishing 6 dp. K/DST now count 13 games, not 16/15, and no value moves. Superflex cannot be reached from the page, so it produces no wrong numbers today; it is a methodology decision.

### Verified (check named)

**Mechanism.** Scratch copies of the origin/main `make sync` dist. In the inline players island I changed one number, Mason's standard espn_ppg: 8.65 -> 8.64 swaps the order, 8.66 does not.
- Headless sweep at standard_10: only RB bias-adjusted values move.
  - Mason fantasycalc_adjusted goes 18.64 -> 7.76.
  - Monangai fantasycalc_adjusted goes 14.59 -> 22.23.
  - The cbs, fantasypros and usatoday adjusted values move the same way.
  - Other RBs move by less than 0.9 through the cell refit.
- Cause: `buildLiveAdjustedMap` takes each player's tier from the ESPN two-tier partition (`ddf.starters` / `ddf.bench`). The partition comes from `buildPositionTiers`, which sorts on espn_ppg, with ties going to the lower player_key. The value is `alpha[pos|tier] + beta[pos|tier] x published`. Mason's FantasyCalc native is 1.2: the starter cell prices it around 18.6, the bench cell around 7.8.
- Ties already resolve deterministically (`stableTiebreak`, and the id tiebreak in buildPositionTiers). The defect is rounding before ranking.
  - The leg (build_ddf_two_tier_leg.py) ranks on the CSV's unrounded rate: Monangai 112.46/13 = 8.6508, Mason 112.41/13 = 8.6469.
  - A locally built standard 10-team leg has Monangai as starter and Mason as bench. The browser on main had the opposite.
- The tiebreaks already agree: both sides sort `(-x, player_key)` numerically.

**Fix.** `PPG_DECIMALS = 6` in pipelines/lib/games_remaining.py.
- Used by bake_players for espn_ppg, blend_ppg, pm_ppg, pm_filled_ppg, rz_ppg and cbsros_ppg.
- Also used by annotate_cbsros_ppg and refresh_players_espn_fields (manual tools).
- Deltas stay at 2 dp. Nothing renders a ppg as text (grep of app/ and app/v2).

**Re-bake.** I used the games-remaining session's read-only stand-in sbclient (Supabase dump via MCP) and its CBS ROS 2026-10-02 snapshot. That dump reproduces origin/main's players.json exactly (players lists equal).
- Fields that changed: the *_ppg precision (max 0.0046), K/DST games_remaining / espn_ros / blend_ros, 0.01 shifts in a few rounded deltas, meta kdst_note and dataset_status.
- 613 players. audit passed.

**Tests.**
- tests/test_ppg_tie_parity.py, in make test-core: the browser split (players.json espn_ppg through the leg's build_position_tiers, which test_ddf_two_tier_leg pins bit-exact to the JS) must equal the leg's, for all 12 combos.
  - On origin/main's players.json it fails at standard 10 (Monangai/Mason) and ppr 14 bench (Helm/Gadsden), and test_ppg_published_unrounded fails (320 players).
  - Restoring `round(v / gr, 2)` on espn_ppg fails test_bake_keeps_precision.
  - Green on the branch.
- tests/test_kdst_games_remaining.py, in make test-core: on origin/main's players.json test_games_follow_the_window fails (Mevis 16, want 13). Green on the branch.

**K/DST.**
- DST: games come from its own team. K: from the registry team, via `_resolve_team_abbr`; a K with no team would use the window length (14). None did: all 45 K resolved to 13.
- 45 K 16 -> 13 and 32 DST 15 -> 13. K/DST espn_ppg is unchanged.
- Browser JS never reads espn_ros. The sweep shows no K/DST move (K/DST are off by default; their values price from ppg).

**12-combo sweep.** `make sync` builds of origin/main and the branch, system Chrome, TradeValueCurveDiagnostics plus all row values.
- fixedPieIndexed is true in all 12 on both builds.
- sourceScaleAgreement is the same on both: true only at ppr_12. This is already the case on main.
- ESPN curve positional starts move by at most 0.1 in every combo.
- Max / median absolute move per source over all players and combos:

| Source | Max | Median |
| --- | --- | --- |
| espn | 2.12 | 0 |
| espn_vorp | 0.07 | 0 |
| cbsros | 0.13 | 0 |
| cbsros_vorp | 2.54 | 0 |
| razzball | 0.13 | 0 |
| as-published charts | 0.10 | 0 |
| fantasycalc_adjusted | 10.89 | 0.005 |
| cbs_adjusted | 9.92 | 0.011 |
| fantasypros_adjusted | 9.01 | 0.006 |
| usatoday_adjusted | 8.84 | 0.003 |

- Every move of 0.5 or more, and why:
  - **standard_10, Mason / Monangai, all four adjusted charts.** Mason fc 18.64 -> 7.75, cbs 20.84 -> 10.92, fp 19.06 -> 10.74, usat 20.95 -> 12.10. Monangai fc 14.59 -> 22.20, cbs 10.60 -> 19.94, fp 11.32 -> 20.33, usat 14.34 -> 22.96. Why: the tier now matches the leg.
  - **standard_10, 11 other RBs, fantasycalc_adjusted, 0.74 to 0.85** (for example Etienne 16.52 -> 15.75, Henderson 16.91 -> 16.08, five bench RBs 5.58 -> 6.43). Why: the RB starter/bench cells refit on the corrected partition.
  - **ppr_14, Helm / Gadsden.** Helm espn 0 -> 2.12 and usatoday_adjusted 0 -> 2.55; Gadsden espn 2.12 -> 0 and fantasycalc_adjusted 1.82 -> 0.10. Why: the bench/waiver split now matches the leg (Helm bench, Gadsden first waiver).
  - **standard_8, every TE, cbsros_vorp, +2.2 to +2.5; also Smith-Njigba -1.1.** Why: Higbee (TE) and Quentin Johnston (WR) tied on bench surplus at 2 dp. With exact rates Higbee takes the last bench slot, so the TE waiver line drops one player. This is browser-only raw value above waivers; there is no server leg to compare against.
  - Role flips with no visible move: Warren / Goedert at espn standard_8 starter-bench (espn_vorp moves 0.07 or less) and cbsros ppr_8 / ppr_14.

**Superflex.** Not reachable by readers:
- curve-widget `setRosterSpot` returns early for any key not in DEFAULT_ROSTER (QB, RB, WR, TE, FLEX, BENCH, K, DST).
- app/v2 only calls `setRosterSpot`.
- `SUPERFLEX` is a boolean read by flexEligible / flexEligiblePositions / isSavedSetup. It makes QB eligible for every FLEX slot. It is not a slot of its own.

**Validation.**
- `CHROMIUM_PATH=<scratchpad chromium> make validate` rc=0, including the two new modules.
- Also failing on origin/main and still failing the same way (re-run in a main worktree): test_jeg68 cbsros markup, test_jeg69 two cases, test_kdst_vorp LAR/WSH. The pinned jeg68/69 numbers moved in the 4th decimal with cbsros precision: 1.005066 -> 1.005209 and 0.839786 -> 0.839902, against pins of 1.000441 and 0.8534, which were already stale.
- Related suites pass: test_ddf_two_tier_leg, test_games_remaining, test_bake_*, test_kdst_* and test_jeg38.
- dist/ and app/ sync output reverted as churn. Committed data: players.json.

### Claimed, not confirmed
- **CBS ROS / Razzball partitions.** These now rank on 6 dp too. Their legs read unrounded snapshot rates, so parity should hold, but no test covers it: the CBS ROS snapshot is gitignored (data/raw).
- **CI bake.** The CI bake (rebuild-chain.yml) runs this code with the real sbclient. That has not been run. The next CI bake will regenerate players.json with whatever data is current then.
- **Hard tiers.** Ties were a rounding artifact, but the hard tier is not. A player whose real ESPN rate crosses the starter line still switches cell and can jump about 10 adjusted points (the same for the raw VORP waiver line, which moves by one player). Avoiding that is a methodology change, for Jeremy:
  - (a) Price adjusted values with a blend of the starter and bench cells. Weight them by the player's starter/bench glide exposure (`sliceExposures`, the same glide that keeps the ESPN price itself continuous). This makes the result continuous in the projection.
  - (b) Fit one cell per position with a starter indicator, and blend only near the line.
  - (c) Keep hard tiers and document the cliff.
- **K/DST inputs.** Their meta says ppg is a weekly mean over weeks 3-18 with the bye counted as 0. That would make it a per-week rate, about 15/16 of a per-game rate, which makes ROS = ppg x 13 slightly low. I did not check this against the weekly data. GAP-029 (frozen 2026-09-21 inputs) still applies.

### JEG332-SUPERFLEX-FLEX options (for Jeremy; nothing changed)
Today no setting reaches superflex, so no number is wrong. If a superflex control ships, these are the choices:
- **A. Dedicated SF slot (recommended).**
  - `shape.SUPERFLEX = n` is a slot count.
  - Fill it after dedicated slots and before FLEX with the best QB/RB/WR/TE by surplus over the positional dedicated-starter baseline (`projectionRoles` already ranks a QB-eligible pool by surplus).
  - In `allocate_flex_vorp_weighted`, allocate SF slots by surplus alone, without the `slots[pos]` weight. That weight is what keeps QBs out today.
  - Python and JS change together, with a VORP_TRANSLATION_VERSION bump.
- **B. Treat SF as QB+1.**
  - Approximate superflex as a second QB slot, the path the QB stepper already supports and which moves the maxes.
  - Simple, and close to real leagues where SF goes to a QB about 95% of the time, but it misprices thin-QB leagues.
- **C. Leave it unsupported.** Remove the dead `SUPERFLEX` flag paths so nothing implies support.

The anchor re-pricing half of the row, where `applyRosterShape`'s top-N factor does not follow WR 3->4, is unchanged and is also a decision.
