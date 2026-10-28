# Claude Code notes for this repo

@AGENTS.md

`AGENTS.md` (imported above) holds every repo rule. This file adds only what
is specific to Claude Code; put shared rules in `AGENTS.md`.

- **User-level rules.** Follow the user-level Linear rules and "Usage
  Discipline" section; the repo rules in `AGENTS.md` override them where they
  differ.
- **Subagents:** `deep-worker` (Opus) only for T1 tickets; `worker` (Sonnet)
  for everything else (tiers in `AGENTS.md`).
- **Rotate the lead thread at about 200k context** (or at each milestone).
  First write the handoff as a comment on the active Linear ticket (state, open
  PRs, next step, decisions pending), then tell Jeremy to start a new thread.
- **Direction questions** may use AskUserQuestion, batched into one ask; the
  multiple-choice rule in `AGENTS.md` still applies.
- **Permissions** are in `.claude/settings.json`: force-push, `reset --hard`,
  `clean -fdx` and `supabase db reset` are denied; migrations, function
  deploys and `gh pr close` ask first.
