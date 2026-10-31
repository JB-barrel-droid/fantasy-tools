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
