## 2026-10-12 - JEG-624 ESPN anchor CSV mixed week windows

Contract: find why the ESPN CSV carried "5-18" and "6-18" together (bake fails closed) and make it carry one window, with a negative-tested guard.

### Root cause
- JEG-574 (#511) made the ESPN puller's ROS window per team: a team that had played its Thursday game started at week 6, everyone else at week 5. From Thursday night to the Tuesday pull the CSV therefore held both windows. `games_remaining.window_from_rows` (bake, DDF leg, fidelity) requires one window and fails closed, so the anchor stopped refreshing.

### Fix
- `pipelines/pull_espn_projections.py`: every row sums the one league window (`ros_weeks`, weeks not played league-wide, MIN_PLAYED_TEAMS). Bye detection scans that window. A Thursday team's played game stays in its ROS until the league rolls over (Tuesday), after which the whole CSV moves to the next window together. Per-team played detection is kept; `team_ros_weeks` helper is kept and still unit-tested.
- Tests in `tests/test_espn_pull_team_played_jeg574.py`: the two main-level assertions that pinned per-team windows (6-18 vs 5-18) were the bug, so they are replaced by single-window assertions. New guard runs the real pull and feeds the CSV to `window_from_rows`.

### Verified (check named)
- `pytest tests/test_espn_pull_team_played_jeg574.py tests/test_games_remaining.py`: 18 passed.
- Negative test: with origin/main's puller restored, `test_csv_carries_a_single_weeks_covered_window` and `test_thursday_teams_share_the_league_window` fail; they pass with the fix. `test_guard_fails_on_the_mixed_state` asserts `window_from_rows` rejects 5-18 plus 6-18.

### Claimed, not confirmed
- The live pull was not run; the next Rebuild comparison chain run should show the ESPN anchor bake succeed.
- Trade-off: until the Tuesday pull, the two Thursday teams' ROS and games_remaining include the already-played game (the JEG-574 behavior for those two teams is traded for one consistent window).
