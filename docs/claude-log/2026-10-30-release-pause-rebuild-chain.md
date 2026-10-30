## 2026-10-30 - Release pause on the new rebuild-chain publish path (JEG-1364, correction to #1125 / JEG-1215)

Contract: #1125 stopped merging onto main after JEG-1206 (f5b6e02d) replaced
the rebuild-chain rebase/push loop with a scratch-worktree publication. Merge
main in normally and re-fit the pause guard so a release window still defers
every automated push to main from that step, without stopping processing.

### Verified (check named)
- Main merged in with a normal merge (73527861), no rebase or force-push. Two
  merge bases (b39fcc32, 6de0bffb) made the recursive base conflict in 22
  unrelated generated files; those are taken as main has them, and this PR's
  24 files were three-way merged against b39fcc32. Real conflicts were
  HANDOFF.md (both kept) and rebuild-chain.yml.
- On that naive merge, `tests.test_main_write_guard` fails 3 tests: the
  existing one-push-per-step check (2 != 1 in rebuild-chain.yml) and the new
  `RebuildChainPublishTest` push-guard and push-pause tests (main fixture
  became NEW during an active pause). After the fix all pass.
- The scratch push now runs `release_push origin "$publication:refs/heads/main"`;
  `release_guard stage` still runs before the candidate commit, the worktree
  and the scratch commit (`test_every_main_push_is_guarded_and_stage_precedes_the_commit`).
- A pause landing on main after the stage check retains the publication and
  exits the step 0 with `pushed=false` and `publication_deferred=true`; main's
  fixture stays OLD and the scratch worktree is cleaned up
  (`test_pause_at_push_retains_the_scratch_publication`,
  `test_pause_at_stage_defers_before_the_candidate_commit`).
- `main_write_guard.py --head` makes the push-phase patch the scratch
  publication against fetched main, not this checkout's candidate commit.
  Without `--head` the retained patch carries this run's own import-health
  report that the publication had dropped in favour of main's newer one (same
  test fails on that assertion).
- `python3 -m unittest tests.test_main_write_guard tests.test_chain_stuck_alert
  tests.test_chain_commits_legs tests.test_rebuild_chain_workflow
  tests.test_rebuild_chain_concurrent_main`: 65 tests OK, including main's
  JEG-1206 and JEG-1308 cases. All workflow YAML parses; `git diff --check`
  clean; `.github/main-write-pause.json` still ships `paused:false`.

### Claimed, not confirmed
- The regeneration handoff dispatch needs no guard: it publishes nothing, and
  the run it starts goes through the same stage and push guards.
- `chain_stuck_alert --published` re-checked against JEG-1308: a failed
  chain's status-only commit takes the age-based failure branch, which ignores
  `--published`; a success that hands off or finds main unchanged leaves the
  alert as it is until a run publishes. No code change.
- CI on the new head and the independent delta review are pending.

### Ported fix (CI on 569a057c)
- `settings-render` failed on 569a057c in `test_round_trips_by_file_and_link`
  (`{}` overrides on the opened link page), the intermittent race JEG-1379
  names; it passed on 62803efa. Ported #1198's `app/v2/league.js` change
  verbatim (read the share link once `TradeValueV2.applyLinkLeague` exists) so
  this PR doesn't wait on #1198; the hunk is identical, so it no-ops once #1198
  merges. `node --check` passes; the render test runs in CI only (no Chromium
  in cloud sessions).
