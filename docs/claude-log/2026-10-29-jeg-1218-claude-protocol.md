## 2026-10-29 - JEG-1218 Claude review and merge protocol

Contract: closed PR #1073 made Codex the release coordinator, which Jeremy
superseded at 19:12 UTC. Carry the rules worth keeping from it into
`AGENTS.md`, updated for Claude-only review and merging, and fix the stale
JEG-1142 block in `HANDOFF.md` that closed PR #1061 was meant to fix.

### Verified (check named)
- Rules carried from #1073 (head `99e75110`, read from its diff): child-ticket
  corrections, the 30-minute branch rule, risk-tier review labels, one
  independent review, at most 8 ready PRs, batches of at most 7 same-risk PRs
  with USO separate, Supabase approvals named each time, weekly/ROS and
  both-sides rules. Not carried: Codex as coordinator, Codex-maintains-HANDOFF,
  the loosened hot-file rule (main's stays).
- Jeremy's 21:08 UTC message "merge anything you recommend once it is green"
  read in the project chat timeline.
- Linear label catalog (list_issue_labels, Jegabee): `Session`, `Model tier`,
  `BE priority` and `needs-review` are retired (2026-10-28); `claude`,
  `needs-jeremy`, `ready-for-claude`, `blocked-dependency` and the
  `review-*` labels are active. AGENTS.md now names only active labels.
- JEG-1142 is Done in Linear (completed 2026-10-28 16:05 UTC); #1044 merged
  as `2e7a2c7` (git log on main).
- `python3 -m unittest tests.test_doc_staleness`: 4 tests OK.
  `git diff --check`: clean. Docs only.

### Claimed, not confirmed
- Whether #1044 was checked on the live site: no live-check record found on
  JEG-1142 or in its logs, so HANDOFF says shipped and Done only.
- Independent Claude review of this PR is still to come.

### Review corrections (independent review of `8b97fecc`, 21:20 UTC)

Verified (re-read of the AGENTS.md hunks; `tests.test_doc_staleness` and
`tests.test_import_health_schema_doc` OK; `git diff --check` clean):
- 1: the yes-each-time rule covers any PR that changes value math or a
  published value, whether or not numbers are claimed to move; routine data
  refreshes on green gates stay excepted as input changes, worded the same in
  the Routing row; backend deploys added next to edge deploys.
- 2: the Branch rule bans pushing straight to `main` and force-pushing, and
  asks for an explicit branch refspec (from #1073).
- 3: the main-merge-only limit applies while another owner still holds a
  branch; a takeover (4 hours idle, owner OK or Jeremy) moves ownership, and
  the taker keeps working the branch with normal main merges only.
- 4: the Muse bullet no longer says it owns `muse`-labeled tickets.
- Nits taken: no-delete rule from #1073, JEG-1173 citation for `session:cma`,
  HANDOFF priorities item 3 now says `needs-jeremy`, ChatGPT/Codex tier
  column marked inactive.
