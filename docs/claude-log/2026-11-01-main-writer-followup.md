## 2026-11-01 - JEG-1441 publication follow-up

Contract: resume the interrupted correction, reject ungated explicit-main
publication in shared workflow steps, and suppress ESPN monitoring writes
in dry mode. #1259 is already merged; use a follow-up draft on
`claude/JEG-1441` rather than rewriting its history.

### Verified (check named)

- GitHub PR readback: #1259 merged as c7ab7562, original branch deleted;
  #1233 remains open. Based this change on current main fe1faaf4.
- Both added workflow regressions failed against unchanged main using
  temporary workflow snapshots, before applying the two condition changes.
- Final focused unittest run: 116 tests passed in 52.633 seconds across
  main_writer_credentials, main_writer_workflows, main_write_guard,
  rebuild_chain_workflow, rebuild_chain_concurrent_main,
  rebuild_chain_consolidation_nonblocking, v2_render_runs_on_data_push,
  deploy_gate_unconditional, espn_ci_workflow, no_failopen_workflows and
  workflow_dispatch_permissions (all tests.test_* modules).
- The first combined run had three contract failures. Recognizing Fidelity's
  existing shared ref-derived environment and updating two consolidation
  mutations to remove the full new condition resolved them. Assertions and
  real-script destination checks remain intact; the final run includes all.
- `actionlint -shellcheck= -pyflakes=` on the two edited workflows passed.
- `git diff --check` passed. Only workflow gates, contract tests and handoff
  documentation change; no source, fixture, scoring or season changes.
- Existing publication mutation still removes the entire commit condition
  and requires the failed-health publication regression to be caught; no
  assertion was removed or weakened.

### Claimed, not confirmed

- Exact-head CI and an independent Claude high-risk review remain gates;
  this author does not supply the independent review.
- No live refresh, Supabase write, settings change, deployment or merge was
  performed. Full make validate is intentionally not run in this task.
