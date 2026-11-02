## 2026-10-31 - Portable coordinator rules / JEG-1445

Contract: carry Jeremy's provider-neutral coordination rules into AGENTS.md and point HANDOFF at PSpice's takeover checklist. Separate review-standard draft; no runtime or bridge changes.

### Verified (check named)
- Source inspection: based on main 76ee1c41, including #1246 review tiers and #1248 usage-crunch review exception.
- HANDOFF.md exists; added default successor and runbook pointer. CLAUDE.md direction-question wording now matches one-at-a-time shared rules.

- git diff --check and Markdown fence inspection passed; HANDOFF runbook link uses the existing PR branch until it lands.
- Browser existence check in the runbook worktree confirmed required Chromium is absent; make validate was not retried and nothing installed.

### Claimed, not confirmed
- No full coordinator dry run or runtime permission enforcement test performed. Cutover high-risk review/merge owner still needs Jeremy's decision.
- Runbook link depends on separate PR #1245 landing; branch/PR fallback is explicit.
