## 2026-10-29 - JEG-1303 (correction child of JEG-1198), PR #1081

Contract: fix the four review findings on PR #1081 at head 5b84ed70 on the same branch, with
no Supabase write and no change to values, defaults or rankings.

### Verified (check named)
- Finding 3: two printed names resolving to one player_key in one list now both go to review
  as `duplicate_player_key` and neither row is written.
  `tests.test_ros_rankings.Saver.test_two_names_for_one_player_key_both_go_to_review` fails on
  5b84ed70 (clean keys `[1, 2]`, expected `[2]`) and passes after the fix.
  `test_same_player_in_two_lists_is_not_a_duplicate` pins that one player in two analysts'
  lists is not a collision. `python3 -m unittest tests.test_ros_rankings`: 24/24 OK.
- Finding 2: `make -n test-unit-modules | grep -c ros_rankings` was 0 on 5b84ed70 and is now
  `python3 -m unittest tests.test_ros_rankings`. `tests.test_run_suite` OK.
- Finding 4: the `claude/JEG-1198-ros-rankings-feed` push trigger and its header line are gone
  from `.github/workflows/ros-rankings-sync.yml`; the workflow guard suites
  (`test_no_failopen_workflows`, `test_workflow_dispatch_permissions`,
  `test_workflow_no_event_interpolation`, `test_ci_speedup_workflows`) OK.
- Finding 1: the saver's docstring now says 015/016 were applied 2026-10-29 on Jeremy's
  "Approve 015 and 016" (quoted from the JEG-1198 comment of 02:58 UTC).

### Claimed, not confirmed
- Full preview CI on the new head (read on the PR checks, not here).
- Live table contents are unchanged by this PR: no write run was made.
