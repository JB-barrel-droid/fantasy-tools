## 2026-11-03 - JEG-860 integration after PR #1255

Contract: resume PR #1284, merge current functional main once normally,
preserve its reviewed publication fix, run focused checks and follow fresh
exact-head CI. Parent owns serial merge/release; no release action here.

### Verified (check named)

- Merged actual main `832a18d90704ffa547ad5aae22e179e28843f3f1`, containing
  PR #1255 `4c60f8fd0e631f3fb961174f9be8f9f77ab67796` and the dispatched
  pipeline-code-hash record, into `1cf4dd75` without conflicts.
- Read independent HIGH-RISK PASS receipt `5745167276` at exact prior head
  `1cf4dd75ddcb056f91f46be3ff7b894137cf7414`. `git diff --quiet` verifies
  `.github/workflows/rebuild-chain.yml`, `tests/test_rebuild_chain_bake.py`
  and `tests/test_rebuild_chain_concurrent_main.py` are unchanged by this
  integration. Publication, failed-validation rollback and race protections
  are preserved.
- Focused raw unittest command: 117/117 passed. Modules:
  `tests.test_baseline_reds`, `tests.test_validate_shards`,
  `tests.test_preview_workflow_matches_pages`,
  `tests.test_deploy_gate_unconditional`, `tests.test_ci_speedup_workflows`,
  `tests.test_draft_ci_workflows`, plus the five JEG-860 behavior regressions
  (green bake, failed validation, restored bake, no-bake publication, newer
  main template regeneration). Draft/head guard messages are expected
  negative fixtures; the command exits zero. No assertions changed.
- Read the new AGENTS baseline-attribution rule and baseline registry
  documentation. Attribution does not waive a failing gate. No registry
  entry or baseline behavior was edited in this PR.
- Whitespace checks pass. No broad local suite was repeated. Existing
  untracked build output was retained; no tracked generated churn arose.

### Claimed, not confirmed

- Fresh exact-head CI and independent integration delta review since
  `1cf4dd75` remain pending. No merge, deployment, job cancellation, deletion,
  production data or access change. Parent owns serial release and will
  check any later main drift; only operational status JSON may use option A.
- After release the first successful chain must still prove committed
  inline-player JSON equals the committed fixture before sync can repair it.
