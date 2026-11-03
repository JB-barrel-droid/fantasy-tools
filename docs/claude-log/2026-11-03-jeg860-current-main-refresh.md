## 2026-11-03 - JEG-860 current-main refresh

Contract: resume the existing PR #1284 lane, reconcile prior head and receipts,
integrate functional main once normally, and verify a minimal focused delta.
Parent retains serial merge/release and post-release parity acceptance.

### Verified (check named)

- Prior head `9386ca19186592040ab15ae08403ff0022f91a3f` has four completed
  successful CI workflows and independent HIGH-RISK integration PASS receipt
  `5746344858`. That receipt remains the delta-review basis, not a review of
  this new head.
- Merged current functional main
  `040474c552a324921bdc7f71008ab6da3f823629` once normally without conflicts.
  Incoming main includes CI-render sharding, accepted UI/test changes and
  input refreshes; none is independently changed by this PR.
- `git diff --quiet 9386ca19 -- .github/workflows/rebuild-chain.yml
  tests/test_rebuild_chain_bake.py tests/test_rebuild_chain_concurrent_main.py`
  passes: the reviewed publication fix and all its behavior regressions are
  byte-for-byte unchanged.
- Focused raw unittest command: 119/119 PASS in 2.606 seconds. Modules:
  `tests.test_baseline_reds`, `tests.test_validate_shards`,
  `tests.test_preview_workflow_matches_pages`,
  `tests.test_deploy_gate_unconditional`, `tests.test_ci_speedup_workflows`,
  `tests.test_draft_ci_workflows`, plus all five publication/failure/race
  regressions (green bake, failed validation, restored bake, no-bake repair,
  newer-main template regeneration).
- No broad local suite or duplicate full validation. Whitespace passes.
  The focused checks created no tracked generated churn; existing untracked
  build outputs were preserved.

### Claimed, not confirmed

- New exact-head CI and independent integration delta review remain pending.
  No source assertion or registry entry changed. No direct main push,
  deployment, cancellation, deletion, production-data or access change.
- After release, the first successful chain still must prove raw committed
  inline-player JSON equals the raw committed players fixture before sync.
