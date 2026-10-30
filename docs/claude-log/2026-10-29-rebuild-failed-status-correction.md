## 2026-10-29 - Failed chain status publishes beside newer inputs (JEG-1308, part of JEG-1206)

Contract: correction from the independent review of PR #1152 at `30ab3fce`.
On a failed chain the commit step stages only status and health, but the new
sort still handed off to a fresh run when a rebuild input moved on main
(fidelity pulse, `data/inputs`, `data/history`, `config/`), so the red status
never reached the monitor. Now a failed chain hands off only for a file it
wrote itself; otherwise its status-only commit publishes on top.

### Verified (check named)

- New `test_failed_chain_status_publishes_when_a_rebuild_input_moves` in
  `tests/test_rebuild_chain_concurrent_main.py` (4 input paths): fails on
  `30ab3fce` (`pushed=false`, `handoff=true` for each path), passes after.
- `tests.test_rebuild_chain_concurrent_main` (8 tests),
  `tests.test_rebuild_chain_workflow`, `tests.test_rebuild_chain_conflict_handoff`,
  `tests.test_chain_commits_legs`, the other rebuild-chain suites and
  `tests.test_validate_shards`: 140 tests OK. YAML parses; `git diff --check` clean.

### Claimed, not confirmed

- CI on the corrected head and a production chain run are still pending.
