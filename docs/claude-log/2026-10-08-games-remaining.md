## 2026-10-08 - GAP-GAMES-REMAINING-STALE fixed (fix/games-remaining)

Contract: verify the stale games-remaining finding against the real schedule,
fix the root cause so per-game rates use the right per-team games in both the
players bake (browser) and the baked ESPN leg, add guards that fail on the
stale state, run the 12-combo sweep main vs branch. Not pushed to main.

### Answer in one line
The finding was right and slightly understated: ESPN's ROS window (weeks
5-18) is 13 games for every team today (no team has had its bye yet), while
players.json divided by 15 (16 for LA/NYG). The flat /16 in the leg was
uniform, so its values were right by accident. Fixed with one shared
games-remaining module (window from the ESPN CSV, byes from a committed table
checked against the Supabase schedule); value moves are entirely the LA/NYG
correction.

### Verified (check named)
- Supabase public.games 2026 (MCP execute_sql): 272 rows, weeks 1-18, every
  team 17 games and exactly one missing week; status 'final' only for week 1
  (16) and 15 of 16 week-2 games (LA-NYG week 2, nflverse 2026_02_NYG_LA, still
  'scheduled'). Old bake count = non-final games = 15 per team, 16 for LA/NYG.
  Byes: CAR/KC 5; CIN/DET/MIA/MIN 6; BUF/JAX/LAC/WAS 7; HOU/NO/NYG/SF 8;
  PIT/TEN 9; CHI/DEN/PHI/TB 10; ATL/CLE/GB/LA/NE/SEA 11; BAL/IND/LV/NYJ 13;
  ARI/DAL 14. Games in weeks 5-18 = 13 for all 32 teams.
- Independent cross-check of the byes: ran pipelines/pull_espn_projections.py
  --force into scratch (vintage 2026-10-07, ROS weeks 5-18); its sidecar
  derives each team's bye from ESPN's weekly projections (team-level zero
  week). 32/32 teams agree with Supabase; sidecar games_remaining 13 for all.
  (The 09-21 kicker weekly file is too noisy to use: injured/cut kickers.)
- ESPN pull played-week detection: a week counts as played once >=20 players
  have actuals, so after Thursday's game ESPN's ROS sums drop the current week
  for every team. That is why the window must come from the CSV's own
  weeks_covered, not from pipelines/nfl_week.py: the content week would say 5
  while the CSV sums 6-18 from Friday to Monday.
- Committed players.json (origin/main 3b550db, baked 2026-10-08 01:53Z):
  games_remaining 15 for 497 skill rows, 16 for 39 (LA, NYG); K 16, DST 15.
- What uses it: bake_players espn_ppg/blend_ppg (browser live ESPN pool,
  two-tier pricing, ESPN value above waivers, published-chart derivation
  projection, disagreement ranks), pm_ppg/pm_filled_ppg, rz_ros/rz_filled_ros
  (Razzball ppg x games), and the ppg deltas. cbsros_ppg and rz_ppg are the
  sources' own per-game numbers (unaffected). No browser JS computes games
  remaining (grep: only product-data.js passes games_remaining through), so
  fixing the bake fixes the browser. The leg builder (ESPN section natives and
  values), build_source_fidelity and test_static_export used ROS/16.
- Fix: pipelines/lib/games_remaining.py + data/inputs/nfl_byes_2026.json.
  bake_players.team_games_remaining verifies the bye table against the
  Supabase schedule (week/home/away, never status) and fails closed on any
  disagreement; build_ddf_two_tier_leg.load_espn_lists and
  build_source_fidelity divide by the same per-team count (teamless rows,
  all ROS 0 today, use the window length).
- Bake reproduction: a read-only stand-in sbclient served Supabase players /
  teams / games / cbs_ros_projections read via MCP execute_sql. origin/main's
  bake with it reproduces the committed players.json exactly (0 player-field
  differences; meta differs only in build time). Branch bake (TZ=UTC): only
  games_remaining, espn_ppg, blend_ppg, pm_ppg, pm_filled_ppg, rz_ros,
  rz_filled_ros and the derived deltas change; audit passes; meta.ros_weeks
  "5-18" added.
- ESPN legs + section rebuilt locally (12 legs, build_espn_section_from_ddf_leg).
  origin/main's process reproduces the committed ESPN section exactly (only
  fetched_at / lineage timestamps). Branch: every value and reindexed number
  identical to main; only natives change (ROS/16 -> ROS/13). Fit
  (build_adjustment_inputs) differs by 1e-14 only; adjusted sections
  unchanged; every other source section byte-identical. Fit outputs reverted
  as churn.
- Browser scale invariance: a scratch build with every team at 15 games vs the
  branch (every team 13) differs by <=0.19 on every source except one rank
  tie (below). So all main -> branch value moves come from correcting LA/NYG
  (+6.25% relative ppg), not the level change.
- 12-combo headless sweep (make sync builds of origin/main and the branch,
  system Chrome, TradeValueCurveDiagnostics). fixedPieIndexed true in all 12
  on both. sourceScaleAgreement identical on both: true only at ppr_12, false
  in the other 11 (pre-existing on main; another agent owns that path).
  Overall peak (sourcePeaks espn) 69.2-70.0 on both. ESPN curve positional
  starts, main -> branch:

  | combo | QB | RB | WR | TE |
  | --- | --- | --- | --- | --- |
  | standard_8 | 40.6->36.4 | 69.9->69.9 | 40.8->42.2 | 23.5->23.3 |
  | standard_10 | 31.6->33.3 | 69.7->70.0 | 40.7->43.4 | 23.5->24.5 |
  | standard_12 | 37.7->40.3 | 69.8->70.0 | 42.4->43.1 | 24.0->23.9 |
  | standard_14 | 41.5->45.1 | 69.5->69.7 | 40.4->41.8 | 19.1->19.5 |
  | half_8 | 38.5->34.6 | 70.0->70.0 | 45.7->47.3 | 28.5->28.1 |
  | half_10 | 26.1->26.3 | 69.5->69.7 | 39.4->39.9 | 26.5->26.4 |
  | half_12 | 34.6->36.8 | 69.8->70.0 | 46.8->47.5 | 25.9->26.0 |
  | half_14 | 35.3->37.7 | 69.2->69.5 | 39.9->40.6 | 26.6->26.6 |
  | ppr_8 | 30.8->27.1 | 69.5->69.6 | 44.9->41.9 | 30.7->29.6 |
  | ppr_10 | 22.1->22.3 | 69.5->69.7 | 41.2->41.8 | 31.7->31.5 |
  | ppr_12 | 27.4->29.6 | 69.7->70.0 | 46.6->47.8 | 29.0->29.2 |
  | ppr_14 | 29.8->31.9 | 69.7->70.0 | 40.6->41.1 | 28.9->29.0 |

  Value moves (max abs / median abs over all players x 12 combos): espn
  4.2/0.15, espn value above waivers 8.0/0.14, cbsros 3.8/0.08, razzball
  4.8/0.10, as-published charts 2.0/0.0, bias-adjusted 10-13/0.15. Biggest:
  Stafford (LA) ESPN value above waivers 0 -> 8.0 (standard_8), 7.7 -> 13.5
  (standard_12); Puka Nacua (LA) +4.5 (ppr_12), +5.5 (standard_10); Nabers
  (NYG) +2.8 (ppr_12); bias-adjusted rank swaps Stafford/Watson (fantasypros
  standard_14 5.6 -> 19.0 / 18.6 -> 6.0) and Nabers (ppr_8 7.7 -> 19.0). The
  ESPN curve's QB start (Josh Allen) moves +2 to +3.6 at 10-14 teams and -3.7
  to -4.2 at 8 teams: cross-position reallocation from the LA/NYG pool change
  (Stafford sits near the 8-team QB line).
- Tests: tests/test_games_remaining.py (added to make test-core). Negative
  checks: restoring the status-count logic in team_games_remaining ->
  test_stale_statuses_do_not_change_games and test_window_after_bye_week red;
  restoring "x": ros / 16 in the leg -> test_bye_week_counts_in_leg and
  test_players_json_matches_leg_per_game red; origin/main's players.json ->
  test_players_json_games_match_window and test_players_json_matches_leg_per_game
  red. All 11 green on the branch.
- Pinned-assertion changes (the divisor itself changed, by design):
  test_static_export ESPN natives check and test_ddf_two_tier_leg's rescoring
  gap now use the per-team count instead of the constant 16.
- build_leg reads csv_meta.get("ros_weeks") so tests/test_espn_pool_cap's
  mocked meta (no ros_weeks) still builds (13 errors before that change).
- `CHROMIUM_PATH=<scratchpad chromium> make validate` rc=0 on the branch.
  tests.test_kdst_vorp fails on origin/main too (pre-existing, not touched).
  app/ and dist/ sync output reverted as churn; committed data:
  players.json (re-baked) and the comparison fixture (ESPN natives).

### Claimed, not confirmed
- The CI bake (rebuild-chain.yml bake_players=true) runs this code
  unchanged: it uses the real sbclient, not the stand-in; the games query now
  selects week instead of status (same table). Not run in CI.
- Merge order: on main's old data the new parity test and test_static_export's
  ESPN-native check are red by design. If main's players.json or ESPN section
  moved before merge, take this branch's code and re-run the bake + chain
  (or rebuild locally as above) rather than resolving the data conflict by hand.
- K/DST still use fixed 16/15 games for their ROS totals (per-game rates are
  unaffected); logged as GAP-KDST-GAMES-FIXED.
- The bias-adjusted rank-tie flip (Jordan Mason / Kyle Monangai, standard_10,
  10.9 points on a 0.01 ppg change) was seen in scratch builds; its mechanism
  was not traced. Logged as GAP-PPG-TIE-FLIP.
- The rendered page was checked only through the headless sweep
  (diagnostics + row values), not visually.
