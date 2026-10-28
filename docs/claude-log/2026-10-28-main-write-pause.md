## 2026-10-28 - Commits-only release switch (JEG-1215)

Contract: implement the approved separate release switch after Pages #1056;
parent owns merge/activation/restoration. One coding session, no subagent fanout.

### Verified (check named)

- Audited main e931b84a: ten main writers, twelve publication blocks; bake and
  Sleeper backfill write branches only. No existing persistent pause control.
- Added default-off `.github/main-write-pause.json` and shared Python guard.
  Publication checks current main before commit and push. Active valid controls
  expire within six hours; malformed/unreachable controls defer publication.
  Deferred staged/committed candidates retain binary patches and metadata as
  workflow artifacts, with visible summaries and warning annotations.
- 107 targeted tests passed: main_write_guard, rebuild_chain_workflow,
  rebuild_chain_conflict_handoff, rebuild_chain_bake,
  rebuild_chain_consolidation_nonblocking, health_artifacts_watch,
  health_artifacts_publish, health_artifacts_summary_step, espn_ci_workflow,
  vintage_trigger (all `tests.test_` unittest modules). YAML parsing, shell
  syntax for all twelve blocks, and `git diff --check` passed. Evidence:
  `/tmp/jeg1215-final-tests.log`.
- Full local make validate was not repeated for this workflow-only change;
  final PR CI and parent review remain required, per the targeted-check brief.
- No pages.yml, Supabase, live settings, schedule or existing run was changed.

### Claimed, not confirmed

- No live activation, restoration cycle or production artifact retrieval tested.
- Parent must coordinate #1054's worktree-publisher overlap and run both suites
  on the integrated version. Current-head CI is required before merge.
- Old-code jobs cannot inherit a newly merged guard; allow them to finish before
  declaring a stable release window. See runbooks/main-write-pause.md.

### Review and shard repair

- Reviewer found computation success could close a publication-stuck alert while
  publication was deferred. Recovery now requires explicit `pushed=true` as well
  as computation success; missing/false publication preserves the alert.
- Job 122946449679 failed two test_chain_commits_legs assertions: its text parser
  selected the newly introduced guard function's else. Anchor parsing at the
  CHAIN_OUTCOME condition; retain success/failure staging assertions.
- 54 focused alert, leg-staging, guard and rebuild workflow tests passed; diff
  check passed. No full local validation repeat, activation or merge.
