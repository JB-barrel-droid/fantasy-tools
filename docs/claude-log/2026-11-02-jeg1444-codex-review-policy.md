## 2026-11-02 - Independent Codex reviews count for merge (JEG-1444 / PR #1279)

Contract: record the existing policy change allowing independent Claude or Codex
reviews at every risk level, and correct the missing per-PR session log reported
in review comment 4438832194. Integrate current main normally while retaining
its cutover ownership, release windows, approval gates and risk floors.

### Verified (check named)
- GitHub PR metadata and review-thread inspection confirmed original head
  `709aab21e5d8c9ab4b86816d71b01eef31521cd3` and the unresolved missing-log
  finding before edits. The separate review receipt on that head reports no
  other blockers; it is historical evidence, not review of this correction.
- `git diff 709aab21^ 709aab21 -- AGENTS.md` confirmed the original policy
  change: independent reviewer jobs/sessions, COMMENT rather than APPROVE,
  Codex eligibility at every risk level without a usage-crunch condition,
  risk-appropriate effort, exact-head green-CI gates, and isolated high-risk
  and value-math releases with value before/after on the ticket.
- `git merge origin/main` integrated main at
  `63bbef495a4828baff8a604b92a2dfe12c469b0f` without rebasing or rewriting
  author history. Manual inspection of `git diff origin/main -- AGENTS.md`
  confirmed the conflict resolutions preserve the existing policy change
  alongside main's cutover and release-window rules. The imported portable
  review-summary bullet now reflects the same review eligibility.

- `git diff --cached --check` passed for the integrated policy and new log.
- A one-off text/structure check confirmed both required log sections and
  byte-for-byte retention of main's deterministic high-risk floor, exact-head
  CI gates, specific approval requirements and cutover section.
- The docs PR's offline CI commands passed locally: 39 tests across
  `tests.test_waivers_mutation_offline_workflow` and the `ClassifierOfflineTests`,
  `AnchorOfflineTests`, and `FixtureOfflineTests` classes in
  `tests.test_waivers_mutation_specificity`.

### Claimed, not confirmed
- Plain `make validate` stopped in `sync` because Playwright's cached browser
  is absent. The diagnosed retry, `CHROMIUM_PATH=/usr/bin/chromium make validate`,
  uses the repository-supported browser override and is still running at
  commit time; a complete gate pass is not claimed here. Generated build
  artifacts are excluded from this correction.
- The original PR description reports `git diff --check` and manual doc
  inspection for the author head; this correction session did not rerun
  checks on that historical checkout.
- No merge, deploy, live-site verification or independent delta review was
  performed by this correction session. New-head CI and the independent
  delta review remain coordinator-owned release gates.

### User-requested addition (2026-11-02 17:41 UTC)

Contract: add Jeremy's two supplied design/working-principle sentences verbatim
in project `AGENTS.md`, on this same owned branch and PR. No global agent file
is involved.

Verified (check named):
- A one-off exact-text check confirmed each supplied sentence appears once
  as a complete line, and removing only the new section reproduces the
  previous committed `AGENTS.md` byte for byte.
- `git diff --cached --check` passed for this follow-up. No existing policy
  content was deleted or rewritten by the user-requested addition.

Claimed, not confirmed:
- Full local validation remains in progress. The earlier green GitHub check
  belongs to `c3f0fc2775cc5d6f82c720026b62ac430d1e3857`, not this follow-up;
  new-head CI and independent delta review are still required.
