# Fantasy Tools Agent Guide

Doc index: `docs/README.md` lists every durable doc; `runbooks/README.md` lists the recurring-job runbooks. Add or retire docs there, not in this file.

`CLAUDE.md` holds the working agreements and is authoritative. This file covers
who does what, delegation and continuity. Dated incident and design notes
(FantasyCalc drift, as-published indexing, VORP>0 calibration, CI sync,
watchdog, cbsros/razzball Supabase wiring) live in `docs/engineering-notes.md`.
Read that file only when your task touches those areas.

## Who does what

Source: Linear document "Board operating conventions (2026-10-10)". Where it
and `CLAUDE.md` disagree, `CLAUDE.md` wins until a ticket changes it.

### Model tiers (the `Model tier` label)

The label is the **minimum** model. Names rot, tiers don't. Pick the best
current model in the lane.

| Tier | Claude subscription | ChatGPT subscription | OpenRouter via opencode / MiniMax | Use for |
| -- | -- | -- | -- | -- |
| **T1 deep** | Opus / Fable, high effort (`deep-worker`) | top GPT / Codex, high reasoning | not allowed | Engine and value math, methodology, any bug with unknown root cause, design, final review of T2/T3 output, every merge and deploy |
| **T2 build** | Sonnet (`worker`) | Codex, medium | a strong open model (checked per task) | Implementation against a written spec: pullers, pipeline stages, migrations, FE built to a contract line, tests. Escalate to T1 after 2 failed gate runs |
| **T3 light** | Haiku, or the `delegate` MCP "fast" tier (JEG-538) | small GPT | cheap OpenRouter models, **MiniMax M3 only** (Jeremy 2026-10-09: 2.5 is out) | Copy edits, doc moves, research sweeps, scraping and capture, triage, repo hygiene, first drafts |

Rules:

1. **Designing or deriving value math is T1.** Anything that decides a
   published value, a curve, a tier, or a waiver line. Executing an approved
   spec (a config switch, porting a rule to a second path, a fixture refresh)
   is T2 with a T1 review at merge. A bug whose root cause is unknown is T1
   until the cause is named.
2. **Other model families never merge.** Their output is a draft PR on
   `be/<ticket>` or `fe/<ticket>`. The Claude lead re-reads the diff, runs the
   gate, and merges.
3. **T3 output is untrusted** until the gate passes. T3 never resolves player
   identity, edits fixtures, or touches `config/` values.
4. A ticket that says T2 but needs a judgement call on the numbers is really
   T1: relabel it.
5. Reviews of T2/T3 work are T1, and are a different model from the author
   where possible.

### Other routing

| Work type | Route |
| --- | --- |
| Review, integration, merge/push/deploy, production QA, scheduled jobs | Claude lead session, T1 (Jeremy 2026-10-06, `docs/decisions.md` ops-ownership-001) |
| Methodology, values, copy, destructive prod actions, outward-facing changes | Jeremy (except routine data refreshes on green gates) |

- **MiniMax: M3 or newer only, for the managed agent's bulk work** (Jeremy,
  2026-10-27, JEG-1173: "open router and my minimax subscription"; "M3, or the
  more recent one Minimax added to the subscription"). Earlier rule (2026-10-09:
  "I only want to use M3 if we use it. 2.5 stinks.") still holds: never M2.5,
  never value math, output untrusted until the gate passes. The lanes/outbox
  dispatch protocol was archived 2026-10-07 (`archive/2026-10-07/lanes/`).
  `lanes/protocol.py` and `lanes/plan_status.py` stay only for existing tests.
- **Muse (Roman)** works here only as a last resort and only when Jeremy asks,
  for example a step that needs Muse's machine. Muse output is untrusted input
  until it passes the repo pipeline. Muse never resolves player identity, edits
  fixtures, triages `review_rows`, pushes to `main`, merges or closes PRs, or
  closes Linear issues.
- **Supabase first** for schedules, checks and orchestration (pg_cron, Edge
  Functions, the `monitoring` schema). GitHub Actions does the site build,
  deploy and repo tests; pg_cron schedules any job that must run in Actions.

## Board operating conventions (Linear, 2026-10-10)

### What a ticket is

One ticket = one outcome, one code path, one PR, about a day of agent work or
less. Anything bigger is a **parent with sub-tasks**. A parent is never worked
directly. It closes when its last child closes.

Every ticket carries:

| Field | Rule |
| -- | -- |
| Title | The outcome, in plain words. No "Facts:", "Back end:" prefixes stacked on prefixes. |
| Why | One or two lines. Link the decision (quote Jeremy with date). |
| Done when | Runnable. Name the test that fails without the change, the check commands (`make validate`, `pipelines/value_check.py compare`, `pipelines/check_rank_guard.py`, 12-combo sweep for chart changes), and for published output the live check. |
| Touches | The hot files it edits (below). Two In Progress tickets may not share a hot file. |
| Labels | exactly one `Session` (owner), exactly one `Model tier`, and for back end one `BE priority`. |
| Milestone | M1 to M5 (below). |
| Relations | `blocked by` for real ordering. Never rely on prose like "after 499". |

### Priority means one thing

* **Urgent**: live numbers are wrong, or deploy is broken. At most 3 open at
  once.
* **High**: on the critical path of the current milestone.
* **Medium**: next milestone.
* **Low**: parked. Nobody picks it up unless the queue is empty.
* **BE priority** (Now / Next / Then / Later) orders the back end within a
  Linear priority. Now means start today.

Status: Backlog = not scheduled. Todo = in a session's queue. In Progress = an
agent is working it now and heartbeats. **In Review = waiting on Jeremy** (with
`needs-review` and the question plus a recommendation in a comment). Done =
merged and live.

### Milestones, in order

1. **M1 Trusted inputs.** No wrong number reaches the page.
2. **M2 One engine, one roster convention.** Expected starts live, JEG-556
   convention, parity test.
3. **M3 Front end on the new engine.**
4. **M4 Research tab.** Quotes no number until M1 and M2 are live.
5. **M5 Documentation store.**

* "Dashboard review: Oct 8 to 9 feedback" stays as the port-the-prototype
  milestone and runs alongside M3.

### Hot files and merge order

**Hot files** (one In Progress ticket at a time): `app/v2/v2.js`,
`curve-widget.js`, `value-model.js`, `value_reference.py` (and its spec
reference), `config/roster.json`, `config/lineup_parameters.json`,
`pipelines/bake_players.py`.

**Merge protocol** (lead only):

1. Merge one engine PR at a time. Re-run `make test-core` after each. Two PRs
   on `curve-widget.js` merged minutes apart broke deploys twice.
2. Merge `main` into the branch (no force-push), then `make validate`. Value
   changes pair JS, Python reference and spec reference on one branch with
   `value_check compare` at 0 and zero rank-guard inversions.
3. Squash-merge as "(JEG-xxx)". Wait for Deploy dashboard. Verify live
   (`verify_live.py`) when published output changed.
4. Heavy suites (render, contract, 12-combo sweep) run on **one machine at a
   time, sequentially**: the Mac or Linux CI, not the laptop with several
   sessions running.
5. Order across lanes: back end engine, then front end that depends on it,
   then copy.
6. The per-PR checks (bot report matches head, `v2-render` green, mergeable,
   the preview run's `make validate` step read, no generated churn, stacked
   order, nav tab count) are in `runbooks/merging-prs.md` (2026-10-22).

### What "accurate values, consistently" requires

1. **Inputs checked before they price anything**: the fidelity pulse and
   per-source tolerances hold a bad source. The divergence check (JEG-460)
   flags a source that disagrees with the others too often, so a
   Razzball-style row shows up in hours, not in a research draft.
2. **One definition per step** (JEG-556): seats, tiers, starter line, waiver
   line, flex. A parity test fails if two code paths disagree.
3. **Every value change** ships with a before/after table on live data, the
   Python reference, `value_check` at 0, the rank guard at 0, and a test that
   fails without the change.
4. **Every bug in a number** gets a row in `docs/risk-register.md` and a
   sentinel row in a fixture, so it cannot silently come back.
5. **No number is quoted in copy or a research post** until the ticket that
   fixes its inputs is live and the readout is re-run.

### Decisions and documentation

Jeremy's answer is quoted on the ticket with the date. The owner removes
`needs-review`, moves the ticket to Todo. A decision that changes a rule also
lands in `docs/decisions.md` (a documentation-store task, M5).

Ticket descriptions are working notes, not the record. A finished fact belongs
in the documentation store (parent ticket in M5). Until the store location is
decided, put it in `docs/` and link it from the ticket.

### Retired

`owner:minimax`, `owner:chatgpt`, `owner:muse`, `owner:claude` labels
(multi-lane policing, retired 2026-10-07 and again here).
`docs/delegation-workflow.md` describes the T1/T2/T3 lanes that replace them.

## Delegating to subagents

- Start from `docs/agent-brief-template.md` (it carries `Touches:`, `Model
  tier:` and the runnable Done-when block). Link to docs instead of pasting
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
