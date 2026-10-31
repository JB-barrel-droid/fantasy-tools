## 2026-10-29 - JEG-1173 jobs deleted, protocol docs reconciled (PR #1107)

Contract: record Jeremy's deletion of the two managed-agent jobs, and finish
the open #1107 review findings on HANDOFF evidence and AGENTS/README
consistency, now that Codex has stepped back.

Correction to `2026-10-29-jeg-1269-cma-evidence-correction.md`: AGENTS.md and
HANDOFF.md are edited in this PR again. Codex no longer coordinates or edits
HANDOFF (Jeremy, 2026-10-29), so the reason for keeping them out is gone.

### Verified (check named)
- Jeremy's words on the project timeline, 2026-10-29 19:18 UTC: "Found it and
  deleted the scheduled jobs." His words, 19:12 UTC: "I want to get off of
  Codex I think, having you use a seperate reviewer makes sense."
- The last `ddf-queue` run comment on JEG-1173 is 19:08 UTC (Linear comments).
- `tests.test_managed_agents_retired`, `tests.test_doc_staleness` and
  `tests.test_run_suite` pass.
- Open PRs that also touch `AGENTS.md`: #1073, #1055 (GitHub REST file lists).

### Claimed, not confirmed
- The jobs are gone. This rests on Jeremy's report; no agent read the
  workspace. A quiet top of the hour afterwards would be corroboration only.
