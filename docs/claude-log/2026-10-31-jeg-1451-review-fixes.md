## 2026-10-31 - JEG-1451 review fixes

Contract: Address all five Claude findings against draft #1260 / 415aa184 in
one push on the existing codex/JEG-1451-fast-gate worktree. Jeremy explicitly
excluded make validate and requested no settings changes, merge or deploy.

### Verified (check named)

- `python3 -m unittest -v tests.test_fast_gate tests.test_fast_gate_dependencies tests.test_draft_ci_workflows`:
  40 passed. New guards discover direct and transitive page readers, report an
  omitted Waivers render test, discover a newly added reader without a hand
  list, keep the test-read document manifest current, and force imported
  pipeline/test helpers to full coverage.
- `python3 -m pipelines.fast_gate run --shard smoke`: 61 passed in 9.3s.
- `python3 -m unittest tests.test_workflow_no_event_interpolation tests.test_workflow_dispatch_permissions tests.test_no_failopen_workflows`:
  8 passed. `actionlint .github/workflows/fast-gate.yml` and `git diff --check`
  passed.
- The retarget test keeps the PR head fixed, changes base ref and SHA, rejects
  stale state and demonstrates a docs-only diff becoming an engine/full diff.
  The edited trigger replans; gate and final verification check live base fields.
- `python3 -m pipelines.fast_gate_history`: same pinned 30 git-derived PR file
  lists now select 28 full, 1 connector plus smoke, and 1 combined finder,
  Waivers and league selection plus smoke; none smoke-only. Expected selections
  and docs/ci/fast-gate-replay.md were regenerated. The two documented follow-up
  audits still omit no broken area.
- Source inventory found 189 imported pipeline modules, 70 imported test
  helpers and 63 test-read documents. Explicit gate infrastructure globs also
  force full coverage. Inert unreferenced session records alone may skip shards.
- Page commands now include whole pytest/unittest modules and known Node
  entry points plus standalone Node test files, preserving former checks. Related routing assertions were
  updated to the review's new shared-file/docs policy; no product assertions
  or baseline registry entries were relaxed. Shared app/v2 paths run full.
- Existing nightly and daily workflows, required-check settings and AGENTS.md
  are untouched. No branches were switched in the shared checkout.

- `node --test tests/test_v2_extract_players.js`: all 33 passed. The source
  audit found this previously unregistered Node entry; automatic discovery now
  includes it in the league shard. The completeness guard also rejects orphaned
  helper readers without a selected executable consumer.

### Claimed, not confirmed

- Expanded page suites were not executed here. The former 6–15 minute estimates
  applied to incomplete lists and are withdrawn; complete coverage needs CI
  measurement. The existing timeout remains fail-closed.
- make validate and contract renders were not rerun, per Jeremy's instruction.
  The earlier unrelated finder keyboard red remains recorded on this PR.
- Independent review of the correction head remains pending. No merge/deploy.
