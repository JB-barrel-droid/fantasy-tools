## 2026-10-26 - Agent handoff doc (Ba-Nana)

Contract: add a root `HANDOFF.md` so another agent (e.g. Muse) can take over
the PM/lead role, plus a one-line pointer in `AGENTS.md`. Docs only.

### Verified (check named)
- Box run launchers and wrapper read directly in `/workspace/logs/` and `~/.config/banana/` on grok-bot-vm (flags and env var names copied, no values).
- Open PR list and merge state: `gh pr list` / `gh pr view` at 7:20 PM CT.
- needs-review and In Review tickets: Linear list_issues (read-only); JEG-1073, 1130, 1131, 1138, 1144 exist (get_issue).
- OpenRouter balance $12.02: `credits.sh`.
- No box runs active: `ps`.
- `main` is not protected and has no rulesets: `gh api .../branches/main`, `.../rules/branches/main`.

### Claimed, not confirmed
- Mac run state, Mac wrapper paths (`claude-minimax`) and the MiniMax/OpenAI budget notes come from Ba-Nana's memory of Jeremy's Oct 26 instructions, not a check this session.
- Product decision summaries are from Jeremy's Oct 26 chat answers as recorded by Ba-Nana; the tickets hold the wording.
