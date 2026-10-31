## 2026-10-31 - Cutover readiness runbook / JEG-1445

Contract: document scope items 1 and 2 only, with a file:line gap inventory. Open a draft review-light PR; no dry run, merge, deploy or bridge/config changes.

### Verified (check named)
- Linear get_issue read JEG-1445, JEG-1444 (including Cutover readiness) and JEG-1440; JEG-1440 was Todo.
- git fetch/worktree setup: base 48c61207, branch codex/JEG-1445-cutover-runbook; upstream unset; git config push.default returned simple.
- Installed Mac bridge capability read: Codex uses existing ChatGPT login, standard speed, durable events and initialized native Linear relay. Tool schemas expose start/status/result; no job launched.
- Source inspection and rg over AGENTS.md, CLAUDE.md, HANDOFF.md and runbooks identified the documented dependencies. HANDOFF.md exists in the current-main worktree; initial older checkout read had failed. Mistaken heavy-suites.md read was corrected to the indexed heavy-suites-and-hot-files.md.

- make validate failed at sync: Playwright chromium_headless_shell-1208 executable is absent. No retry or browser installation. Generated app/dist files remain unstaged in this isolated worktree; only the three requested docs are committed.

### Claimed, not confirmed
- Dots and Muse capabilities are charter-reported; no independent integration check here.
- New coordinator end-to-end pickup and bridge recovery are untested; JEG-1445 item 3 and JEG-1440 remain separate work.
- Review/merge replacement and weekly-limit threshold require Jeremy's decision.
