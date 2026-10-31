## 2026-10-29 - Rebuilds survive main moving under them (JEG-1206)

Contract: a validated rebuild must not be dropped when another job pushes a
generated file meanwhile (run 40689076971: validation passed, the rebase
conflicted on `dist/modules/source-import-health.json`, and the handoff was
skipped because another run was waiting). One clean PR from current main,
taking over from Codex's #1054 (#1063 and #1070 carried the same commit-step
change mixed with JEG-1215 and JEG-1203 work). No rebase, no merge, no
force-push; one publication commit and one Pages dispatch.

What changed in `.github/workflows/rebuild-chain.yml` "Commit and push if
changed": each try fetches main and sorts what changed since the run's base.
A monitor report this run also wrote (import health, Actions status,
checkpoints, monitoring summary, ops status) is kept as main has it and the
rest publishes. A rebuild input or output (fixture, `data/history`,
`data/ddf-two-tier`, `data/inputs`, `config/`, fidelity pulse, the chain's own
dist files) or any other overlap hands off to a fresh run from current main,
with the dispatcher's real result in the summary. Anything else (code, docs,
other reports) stays as main has it and the rebuild publishes on top. The
commit is built in a scratch worktree; a rejected push re-sorts from the new
tip; a lost push reply is confirmed on main before any retry. The candidate
patch is uploaded as the `rebuild-publication` artifact.

### Verified (check named)

- `python3 -m unittest tests.test_rebuild_chain_concurrent_main`: 7 tests pass
  (the 40689076971 case, a code edit on main, five rebuild-input paths, a real
  push-time race, a lost push reply, a failed chain beside a newer monitor, and
  a static no-rebase/no-force check).
- The same module against `origin/main`'s workflow: all 7 tests fail
  (10 failures counting subtests; only the `data/history/index.json` input
  subtest passes there, because the old rebase conflicts on it).
- Existing workflow suites still pass: `tests.test_rebuild_chain_workflow`,
  `tests.test_rebuild_chain_conflict_handoff`, `tests.test_chain_commits_legs`,
  `tests.test_rebuild_chain_bake`, `tests.test_rebuild_chain_failclosed`,
  `tests.test_rebuild_chain_source_resiliency`,
  `tests.test_rebuild_chain_per_source_hold`,
  `tests.test_rebuild_chain_consolidation_nonblocking`,
  `tests.test_validate_shards`, `tests.test_workflow_dispatch_permissions`,
  `tests.test_chain_stuck_alert`, `tests.test_ci_speedup_workflows`: 170 tests OK.
- Wired into `test-core` and `test-core-shard-1` (next to
  `tests.test_chain_commits_legs`); `tests.test_validate_shards` passes.
- Workflow YAML parses; the extracted commit script passes `bash -n`;
  `git diff --check` is clean.

### Claimed, not confirmed

- `make test-core-shard-1` was not run green locally: it stopped at
  `tests.test_static_export` because this checkout's `dist/` was not rebuilt
  with `make sync` (fixture dated 2026-10-29, dist 2026-10-26). Unrelated to
  this change; preview CI runs `make sync` before the shards.
- Not run in production. JEG-1206 is done only after a merged chain run
  publishes and the live history index matches the committed one.
