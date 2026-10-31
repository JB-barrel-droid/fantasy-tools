# Claude Code notes for this repo

@AGENTS.md

`AGENTS.md` (imported above) holds every repo rule. This file adds only what
is specific to Claude Code; put shared rules in `AGENTS.md`.

JEG-1466 (Jeremy, 2026-10-31: "Ok, so set up best practices then"): follow
`AGENTS.md`'s freshness gate, merge-main/no-rebase, unchanged-patch re-review,
Linear handoff and 6 AM/4 PM Central approval-window rules before promotion
or merge; the Oct 29 standing OK does not create an auto-merge path.

- **User-level rules.** Follow the user-level Linear rules and "Usage
  Discipline" section; the repo rules in `AGENTS.md` override them where they
  differ.
- **Implementation subagents:** `deep-worker` (Opus) for T1 tickets;
  `worker` (Sonnet) for everything else (implementation tiers in `AGENTS.md`).
- **Review subagents:** use the capability tiers and current model mapping in
  `AGENTS.md`: high-risk review, value math and design need deep reasoning;
  light, standard and small delta reviews use the mapped standard capability.
  Apply its coordinator risk label, deterministic high-risk floor, pushed-head
  green-CI prerequisite, escalation handoff and current-head receipt rules.
  Implementation tiers remain separate from review risk tiers.
- **Rotate the lead thread at about 200k context** (or at each milestone).
  First write the handoff as a comment on the active Linear ticket (state, open
  PRs, next step, decisions pending), then tell Jeremy to start a new thread.
- **Direction questions** may use AskUserQuestion, batched into one ask; the
  multiple-choice rule in `AGENTS.md` still applies.
- **Permissions** are in `.claude/settings.json`: force-push, `reset --hard`,
  `clean -fdx` and `supabase db reset` are denied; migrations, function
  deploys and `gh pr close` ask first.
