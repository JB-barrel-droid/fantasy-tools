## 2026-10-29 - JEG-1218 protocol corrections

Contract: correct existing PR #1073 before any next release, preserving unrelated content and all runtime files. Implement the consolidated ticket correction checklist and Jeremy's explicit 18:08 UTC release limits, rather than appending conflicting overrides.

### Verified (check named)

- Ticket/remote reconciliation found the existing Codex branch at `fef356ee84d5fd45041127274435e9983ebfe20a`, with no newer corrective writer. The previous commit was authored at 03:50:16 UTC; the corrective claim was posted at 18:10:32 UTC as Linear comment `f507cb3d-49da-43e8-9968-6a6f5886b821`. Immediate comment/ref rereads found no competing claim or push. Current main `430791c41ca9578d878c14c3a37d37a0f3fe0670` merged normally and cleanly.
- In-place corrections retire Claude-only release routing, mandatory legacy Session/Model-tier/BE-priority ownership gates, CMA takeover and blanket shared-file exclusion. Existing domain/model capability guidance and unrelated history remain.
- Policy text includes audited readiness, explicit corrective children on the same branch/PR, exact-head independent review receipts, material-delta review, the narrow typo exemption, weekly/ROS separation and both-team Natural fit. JEG-1217 remains Claude-owned dashboard-first implementation without new math/design authority.
- Jeremy's three approved limits are recorded: claimed main-only cross-agent merges after 30 minutes without owner push or owner OK; at most seven same-risk PRs on pinned current main with combined CI and focused integration review; exact-SHA/synthetic docs/tests verification versus named browser journeys for bench values, JSN discovery, pricing context and large UI. Whole-batch rollback uses a revert PR; USO stays separate; no moving-main data exemption or changed Supabase/deletion permissions.
- #1107 metadata and the JEG-1269 handoff confirm the offered retirement text, with runtime/script changes retained on its author's branch. Managed-agent retirement is distinct from the explicitly UNVERIFIED deployment pause state. #1055 remains a separately owned overlap, not a branch changed here.
- `python3 -m unittest tests.test_doc_staleness`: four tests PASS. The report's informational historical staleness findings are not release success claims. `git diff --check` passes. Scope is AGENTS.md, HANDOFF.md and this required per-session log, with no runtime/data/workflow change or file deletion.
- Read-only #1117 reconciliation confirms it is unmerged at `37b49b6e41c9a6345ce7da56e4839ca0b5754cb3`. Its merge is paused until protocol #1073 is published and verified.

### Claimed, not confirmed

- Independent protocol review, current-main health/freshness, applicable exact-head CI, publication and synthetic verification are still pending at this checkpoint. Previous review receipts do not approve this material protocol delta; AGENTS/protocol changes are not review-exempt.
- Repository metadata has `delete_branch_on_merge=true`. Specific automatic-cleanup approval for #1073 is absent, so merging is held while its branch is retained; no cleanup authority is inferred from other PR approvals.
- No authenticated managed-agent paused-state reads or active-run inventory were performed. The separate operational pause remains unverified. No Supabase operation, direct main push, force push or deletion occurred.

### Later preflight checkpoint (2026-10-29)

- Independent substantive review and focused corrective-delta review PASS on `18a84af266195cb174f1b8ee3d48a8ab39154df3`; unconditional integration claims and fresh named Supabase approval were the two findings resolved. Final-head doc-staleness tests passed (four tests, 0.001 seconds), with scoped whitespace checks and a clean worktree.
- The coordinator subsequently forwarded specific approval for automatic deletion of `codex/JEG-1218-two-agent-protocol` when #1073 merges. The earlier absence noted above is historical; other deletion/Supabase permissions are unchanged. HANDOFF's current status is corrected accordingly.
- Main `430791c4` build and all four validation shards passed; its deploy job remained queued at the last read. No #1073 merge, exact-SHA publication or synthetic success is claimed at this checkpoint. #1117 remains unmerged/paused; no batch cut has begun.
