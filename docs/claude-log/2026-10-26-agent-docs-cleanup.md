## 2026-10-26 - AGENTS.md / CLAUDE.md merge and cleanup (Ba-Nana)

Contract: make `AGENTS.md` the one canonical rules file, reduce `CLAUDE.md` to
an `@AGENTS.md` import plus Claude Code specifics, and remove only verifiably
stale lines (Jeremy, 2026-10-26: "make sure they are the same, and get rid of
old stuff"). Docs only.

### Verified (check named)
- Every path the two files cite exists, except `dist/static`, `dist/server`,
  `space.json`, `deploy.sh` (intentionally gone; the "do not re-add" rule stays)
  and `docs/claude-log.md` (moved to `archive/2026-10-12-docs/`): `ls` loop.
- `tests/test_lane_protocol.py` still imports `lanes.protocol`: `grep`.
- Linear (read-only `get_issue`): JEG-440 Done, JEG-584 Done 2026-10-12 (comment:
  "M3 only, later reversed: MiniMax is not used"), JEG-538 Canceled, JEG-1086
  Done, JEG-1107 In Review.
- Linear milestones M1, M2, M3, M5 and "Dashboard review: Oct 8-9" at 100%,
  M4 at 85%: `list_milestones`.
- `owner:*` labels retired; four `session:*` labels exist: `list_issue_labels`.
- https://jb-barrel-droid.github.io/fantasy-tools/value-logic/ returns 200: `curl`.

### Claimed, not confirmed
- The MiniMax-until-Oct-31 and DeepSeek routing, and Ba-Nana as PM, come from
  Jeremy's 2026-10-26 chat as recorded by Ba-Nana; not yet on a ticket.
- Whether the claude.ai artifact's daily republish task has been retired.

### Follow-up: merge order (same PR)
- Jeremy, 2026-10-26: always merge `origin/main` into branches, never rebase,
  never force-push. AGENTS.md merge step 2 and `docs/merge-charter.md` queue
  step updated; `rg -i rebase` over AGENTS.md, CLAUDE.md, docs/merge-charter.md,
  docs/delegation-workflow.md, docs/agent-brief-template.md, runbooks/ is empty.

### Follow-up: final check before merge (Claude)
- Pointers that named `CLAUDE.md` for rules now in `AGENTS.md` updated in
  `docs/agent-brief-template.md`, `docs/README.md`, `docs/merge-charter.md`.
  Verified: `git diff origin/main...HEAD --stat` is docs only.
- PR #939 (JEG-1107) was still open, so its values-explainer sentence is not
  in `AGENTS.md` yet; it lands when #939 merges main in.
