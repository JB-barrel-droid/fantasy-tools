## 2026-10-31 - Baseline red registry / JEG-1450

Contract: add model-free attribution without excusing failures; open a draft only.

### Verified (check named)
- 106 tests pass: baseline_reds, draft_ci_workflows, preview_workflow_matches_pages, ci_speedup_workflows, validate_shards, deploy_gate_unconditional.
- Forced known/new failures retain exit 1 and appear in stdout and the job summary.
- Unit tests cover environment matching and explicit consecutive-night green evidence.
- bash -n, py_compile, git diff --check and BASH_ENV make dry-run pass.
- Linear: JEG-1394 remains In Progress; JEG-1450 set In Progress; draft marker absent before work. Finder search found no dedicated open owner.

### Claimed, not confirmed
- make validate deferred to CI: Playwright Chromium headless-shell executable absent on Mac (launch probe failed).
- Initial broader check included test_render_sweep_shards: failures in untouched Makefile shard coverage (JEG-1231 modules not in full extra list); not modified here.
- Recent CI history REST lookup rate-limited. GraphQL #1240 receipts available, heavy jobs skipped; current main has no rollup. Seed scope stays local.
- Three-night persistence and workflow execution require CI. AGENTS.md reviewer line deferred until #1250 merges.

## Review fixes (JEG-1450)

### Verified (check named)
- 115 tests pass across baseline_reds, run_suite, draft_ci_workflows, preview_workflow_matches_pages, ci_speedup_workflows, validate_shards and deploy_gate_unconditional.
- Added malformed-registry/output passthrough, mixed known/non-unittest failure, green exit, signature mismatch, expired entry and context-specific removal coverage.
- Failed gate exit status is preserved; invalid registry returns 2 only when the gate itself passed.
- py_compile, bash -n and git diff --check pass. AGENTS.md untouched.

### Claimed, not confirmed
- make validate remains unrun: prior Chromium headless launch probe showed the executable missing; no browser installation or repeat probe.
- Workflow execution and actual three-night history still require CI. Conservative enclosing-gate warning deliberately avoids claiming complete attribution from runner summaries alone.

## Mac continuation (2026-11-02, JEG-1450)

### Verified (check named)
- Merged origin/main 5381de25 normally; draft PR #1255 reused.
- 115 focused checks pass (baseline_reds, run_suite, draft_ci_workflows,
  preview_workflow_matches_pages, ci_speedup_workflows, validate_shards,
  deploy_gate_unconditional). After adding seed coverage, baseline_reds: 9 pass.
- Added local-only recorded journey, market-sort and missing-Chromium seeds.
  Seed test checks known attribution, CI isolation and signature mismatch.
- git diff --check passes. HANDOFF.md absent from PR diff.

### Claimed, not confirmed
- make validate not run: pgrep found active JEG-1363 and JEG-1403 validations.
- Current-head remote CI and independent review remain required.
- Missing-Chromium attribution temporarily owned by JEG-1450; a dedicated
  environment ticket may replace it. No registry entry removed.

Next turn: inspect final-head CI, complete independent review, and confirm
Chromium environment ownership before any approved batch merge.
