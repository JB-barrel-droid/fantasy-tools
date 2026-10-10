# Fantasy Tools Agent Guide

`CLAUDE.md` holds the working agreements and is authoritative. This file covers
who does what, delegation and continuity. Dated incident and design notes
(FantasyCalc drift, as-published indexing, VORP>0 calibration, CI sync,
watchdog, cbsros/razzball Supabase wiring) live in `docs/engineering-notes.md`.
Read that file only when your task touches those areas.

## Who does what

| Work type | Route |
| --- | --- |
| Engine/value math, methodology, debugging with an unknown root cause, design, final review | Claude, Opus (`deep-worker` agent) |
| Routine implementation with a clear spec, pullers, migration files, tests, docs, QA runs | Claude, Sonnet (`worker` agent); escalate to Opus after 2 failed gate runs |
| Review, integration, merge/push/deploy, production QA, scheduled jobs | Claude lead session (Jeremy 2026-10-06, `docs/decisions.md` ops-ownership-001) |
| Methodology, values, copy, destructive prod actions, outward-facing changes | Jeremy (except routine data refreshes on green gates) |

- **MiniMax is not used** (Jeremy, 2026-10-09: "minimax makes mistakes on
  everything it touches, and I only want to use M3 if we use it. 2.5 stinks.").
  The lanes/outbox dispatch protocol was archived 2026-10-07
  (`archive/2026-10-07/lanes/`). `lanes/protocol.py` and `lanes/plan_status.py`
  stay only for existing tests.
- **Muse (Roman)** works here only as a last resort and only when Jeremy asks,
  for example a step that needs Muse's machine. Muse output is untrusted input
  until it passes the repo pipeline. Muse never resolves player identity, edits
  fixtures, triages `review_rows`, pushes to `main`, merges or closes PRs, or
  closes Linear issues.
- **Supabase first** for schedules, checks and orchestration (pg_cron, Edge
  Functions, the `monitoring` schema). GitHub Actions does the site build,
  deploy and repo tests; pg_cron schedules any job that must run in Actions.

## Delegating to subagents

- Start from `docs/agent-brief-template.md`. Link to docs instead of pasting
  them.
- Keep tasks narrow and output-oriented. Treat agent results as raw material:
  the lead re-reads touched files and runs the gate before integrating.
- Ask for one output shape: findings with file:line refs, options with a
  recommendation, a minimal patch, a debugging trace, or a risk list.
- For review-only work, say "do not edit files" rather than removing tools.
- Don't delegate small edits or anything where the brief takes longer than
  the work. More templates: `docs/delegation-workflow.md`.

## Continuity

GitHub and Linear hold the state, never a chat thread. Switching sessions or
harnesses should cost about 10-20 minutes:

- Start by checking `git status` and recent commits.
- Commit and push validated slices promptly.
- If a slice can't be committed yet, leave a handoff (Linear comment or doc)
  with state, changed files, commands run, failures and the next action.
- Don't leave decisions only in chat.

## Validation

`make validate` is the deploy gate (see `CLAUDE.md`). For narrower work, run
the smallest meaningful command first, then `make validate` before publishing.
`dist/` is generated: edit sources or fixtures, then run the sync/validation
path.
