## 2026-10-30 - Hold only the failing source after a red validate, on current main (JEG-1203, JEG-1204, part of JEG-1201)

Contract: carry the orphaned Codex isolation work (#1050, #1051, and the
workflow half of #1070) onto current main as one Claude-owned PR, without
#1070's JEG-1206 retry and JEG-1215 pause parts, which main already carries
(f5b6e02d, #1125). Jeremy instructed this (2026-10-30 17:02 UTC). No value
math, no deploy, no Supabase change.

What it does: when `make validate` goes red after a rebuild, the chain asks
`pipelines/isolate_post_validate.py isolate` to name one fully attributed,
changed source. That source alone goes back to its last published section
(marked held); the complete gate then runs once more and the fixture
publishes only after `confirm`. Any decline, isolator error, red retry or
confirm failure keeps the original red status and blocks the fixture, as
today. The JEG-1204 held-source matrix (`tests/_hold_scenarios.py`,
`tests.test_seeded_hold_build`) rides along.

Branch: `claude/project-thread-n1r1o8` = origin/main b3eb8d97 + merge of
`be/jeg-1201-post-validate-culprits` (bec87317, #1050 incl. #1051) + a port
of 63afba27's workflow hunk and wiring test.

### Verified (check named)
- `tests.test_post_validate_workflow_wiring`: 5 failures on main's
  rebuild-chain.yml (b3eb8d97), 5 OK on this branch.
- `python3 -m unittest tests.test_isolate_post_validate tests.test_post_validate_workflow_wiring tests.test_rebuild_chain_workflow tests.test_record_post_rebuild_validation tests.test_rebuild_chain_per_source_hold tests.test_validate_shards tests.test_player_aliases tests.test_main_write_guard tests.test_rebuild_chain_conflict_handoff`: 121 OK, after registering the wiring test in test-core (test_validate_shards caught it missing).
- Merge conflicts were only in `docs/picks-log.md` and `HANDOFF.md` (notes);
  both sides kept, #1070's JEG-1206/1215 integration notes dropped.
- Sleeper identity refresh after #1209: manual dispatch on main
  (run 41098267164) passed and committed 5eb56620; `meta.pulled_at`
  2026-10-30T17:22:40Z. In the new base Jalen Hurts reads IR, depth 2; the
  bake's `nfl_universe.active_universe` maps that to `injured_reserve`.

### Claimed, not confirmed
- `data/fixtures/current/players.json` still shows the 2026-10-09 roster
  status (Hurts `active_roster`, depth 1) until the next rebuild-chain bake
  reads the refreshed base.
- The browser half of the JEG-1204 matrix needs Playwright, which this cloud
  session can't install; CI's required render job runs it.
- The recovery path has never run on a real red rebuild; first live use is
  the next red validate after merge.
