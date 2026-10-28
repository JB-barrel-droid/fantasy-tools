# Fantasy Tools Agent Guide

Agents taking over PM/lead work: read `HANDOFF.md` first.

This is the one rules file for every agent in this repo (Claude Code, Codex,
Cursor, Muse, OpenRouter and MiniMax runs). `CLAUDE.md` imports it with
`@AGENTS.md` and adds only Claude Code specifics. Edit rules here, not there.

Doc index: `docs/README.md` lists every durable doc; `runbooks/README.md` lists
the recurring-job runbooks. Add or retire docs there, not in this file. Dated
incident and design notes (FantasyCalc drift, as-published indexing, VORP>0
calibration, CI sync, watchdog, cbsros/razzball Supabase wiring) live in
`docs/engineering-notes.md`; read it only when your task touches those areas.

## Pre-launch: ship, and keep the numbers honest

Jeremy, 2026-10-07: no users yet, and the late-September multi-agent policing
is retired. Get fresh data live every week, protect only what keeps the numbers
honest, refine methodology after launch. Linear is the source of truth.
Parallel work is uncapped (Jeremy, 2026-10-09), limited only by: no two agents
on one code path, value changes paired with the Python reference on one branch,
merges ordered so main stays green.

## Model tiers and responsibilities

Choose the minimum model capability from the task, not a Linear label:

- **T1 deep:** value/engine math, methodology, unknown-root-cause debugging,
  design, independent review, every merge and deploy.
- **T2 build:** implementation against a written spec. Escalate to T1 after
  two failed gate runs or when a published-number judgment is needed.
- **T3 light:** copy, docs moves, research collection, hygiene and first drafts.
  Never resolve player identity, edit fixtures or config, or change value math.

Executing an approved value spec is T2 with T1 review. Other model families
produce draft PRs; the Claude lead re-reads the diff, runs the gate and merges.
T3 output is untrusted until the gate passes. Prefer a different model for
independent review. MiniMax is M3 or newer only, never M2.5 or value math.

Jeremy decides methodology, published-value rules, copy/product decisions
and destructive production actions. Engineering choices stay with the lead;
check existing decisions before asking again. Reversible picks may follow
HANDOFF.md's newer logged-pick rule; a pick is not a deployment approval.

Supabase first for schedules/checks/orchestration (pg_cron, Edge Functions,
monitoring); GitHub Actions builds/deploys/tests. The lanes/outbox dispatch
protocol is retired; lanes/protocol.py and plan_status.py remain for tests.
Old named harness/session assignments are history, not current ownership.

## Linear (team Jegabee, project Trade Value Chart)

Source: Linear document "Board operating conventions (2026-10-10)", folded in
here. Ticket per workstream, status comments, quoted decisions, agents name
their ticket, PR titles carry "(JEG-xxx)" or "(part of JEG-xxx)".

- The back end owns tickets for pipelines, Supabase, engine math and
  workflows. Each front-end session owns its own tickets. Front-end requests
  that need engine or data changes become back-end tickets, linked to the
  front-end ticket.
- Fidelity findings from the pulse, an audit or a reviewer get a ticket
  (Urgent if live numbers are wrong) and a row in `docs/risk-register.md`.

### What a ticket is

One ticket = one outcome, one code path, one PR, about a day of agent work or
less. Anything bigger is a **parent with sub-tasks**. A parent is never worked
directly. It closes when its last child closes.

| Field | Rule |
| -- | -- |
| Title | The outcome, in plain words. No "Facts:", "Back end:" prefixes stacked on prefixes. |
| Why | One or two lines. Link the decision (quote Jeremy with date). |
| Done when | Runnable. Name the test that fails without the change, the check commands (`make validate`, `pipelines/value_check.py compare`, `pipelines/check_rank_guard.py`, 12-combo sweep for chart changes), and for published output the live check. |
| Touches | The hot files it edits (below). Two In Progress tickets may not share a hot file. |
| Labels | Bug, Feature or Improvement only. Owner/session, wave, BE queue, model-tier, review and prototype labels are retired by Jeremy's Oct 28 cleanup; do not recreate them. |
| Milestone | The current project milestone in Linear (M1 to M3 and M5 are complete; M4 Research tab is open). |
| Relations | `blocked by` for real ordering. Never rely on prose like "after 499". |

### Priority and status

* **Urgent**: live numbers are wrong, or deploy is broken. At most 3 open at once.
* **High**: on the critical path of the current milestone.
* **Medium**: next milestone.
* **Low**: parked. Nobody picks it up unless the queue is empty.

Backlog = unscheduled; tracking parents are not direct work. Todo = ready to
resume, including finishing a handed-off PR. In Progress = actively worked.
In Review = a real unresolved decision or explicit hold, with
context/options/recommendation in the current brief. Done = merged and live.

### Ownership and handoff

Use the groomed Linear queue and current PR activity, not old session labels.
The assignee remains Jeremy; record the actual active worker and branch in
one current status summary. Before claiming, check for overlapping hot files
and an active heartbeat/commit/PR update within four hours. Do not overwrite
another worker's current work; coordinate first. Jeremy can authorize takeover.

Claim a Todo ticket by setting In Progress and recording its branch.
Choose sufficient model capability from the scope; do not add a tier label. Update the same status summary on meaningful state changes and
at least every four active hours; push validated work so it is recoverable.
Do not append repeated routing, waiting or retry memos. When stopping, leave
current state/branch/next check and return the ticket to Todo.

Retired harnesses have no standing permission to reclaim tickets. JEG-1173
tracks managed-agent teardown; do not infer schedules stopped from retirement.

### Decisions go to Jeremy as multiple choice

Product, copy and method choices that are his are posted on the ticket as
options with context and a recommendation; use the newer logged-pick exception
in HANDOFF.md only where authorized. Record the question/hold in the brief,
move the ticket to In Review, and claim the next ticket rather than waiting. Batch questions and
never repeat one he has answered; check the ticket first. When he answers, the
owner folds the dated decision into the current brief and moves the
ticket back to Todo (or In Progress if it resumes now). A decision that changes
a rule also lands in `docs/decisions.md`. Pre-launch, block only on wrong
numbers and finish end to end.

Keep the ticket/PR brief concise and current; synthesize settled discussions
there, with links to evidence. A durable technical fact belongs in docs/
(indexed in docs/README.md). For selective review reading and comment hygiene,
see docs/review-context.md; old memos are not default review context.

## Hot files and merging

**Hot files** (one In Progress ticket at a time): `app/v2/v2.js`,
`curve-widget.js`, `value-model.js`, `value_reference.py` (and its spec
reference), `config/roster.json`, `config/lineup_parameters.json`,
`pipelines/bake_players.py`.

**Merge protocol** (lead only):

1. Merge one engine PR at a time. Re-run `make test-core` after each. Two PRs
   on `curve-widget.js` merged minutes apart broke deploys twice.
2. Bring the branch up to date by merging `origin/main` into it. Never
   rebase, never force-push (Jeremy, 2026-10-26). Then `make validate`
   and the contract test (`tests/test_v2_contract_render.py`). Value changes
   pair JS, Python reference and spec reference on one branch with
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
   order, nav tab count) are in `runbooks/merging-prs.md`.

## Standing constraints

- **Finish end to end.** For a fix, refresh or deploy repair: commit, merge to
  `main`, wait for GitHub Actions, and check the live site when published
  output changes. Stop only if Jeremy says not to publish, the change needs a
  force push or history rewrite, or it is a production Supabase schema change
  he hasn't approved.
- **Block only on the data math.** `make validate` is the deploy gate. It runs
  the build plus `make test-core`: curve shapes and starts, missing values
  never shown as zero, source integrity, and the published surfaces the page
  needs. The full suite (`make test-unit`) runs in preview CI and does not
  block. Staleness, review holds, coverage drift, import health and monitoring
  are warnings: label them on the page and don't stop the site. For narrower
  work, run the smallest meaningful command first, then `make validate`.
- **A shorter or longer chart list is filled in, not held.** Jeremy,
  2026-10-16: "When lists get longer or shorter we need to follow the
  conventions we've set, filling in where needed from other charts to get to
  full rosters in leagues." The fill-in rule (OC-5, VP-2.4) fills the chart to
  the league's rosterable set; the review passes the list and names the
  changed players as a warning. Hold only when fill-in cannot reach the
  rosterable set or a dropped player is still priced live. Don't ask Jeremy
  for a floor accept when fill-in covers it. `runbooks/source-held.md` 3b.
- **Bug fixes ship with a test that fails without the fix.** That test is the
  proof. No PR checklist or written proof is needed.
- **Do not adjust tests to go green.** If a test fails, assume the code is
  wrong. Change an assertion only when the assertion itself was wrong or the
  rule it pins was changed by Jeremy, and say which in the commit message.
- **Every session that changes anything writes a log entry** in
  `docs/claude-log/YYYY-MM-DD-slug.md` (Jeremy, 2026-10-23, JEG-975: "1 - A").
  One file per PR, with "Verified (check named)" separate from "Claimed, not
  confirmed"; the format is in `docs/claude-log/README.md`. The commit message
  and PR description say the same in short.
- **`make sync` is the single publish path** and stamps the build tag. `dist/`
  is generated: edit sources or fixtures, then run sync. Do not re-add
  `dist/static`, `dist/server`, `space.json` or `deploy.sh`.
- **Do not touch `~/Projects/"fantasy tools"`** on the user's machine beyond the
  `Claude outputs/` folder. It holds `data/raw` (33MB, gitignored), the only
  copy of the player-news pipeline's inputs.

## Accurate values, consistently

1. **Inputs checked before they price anything**: the fidelity pulse and
   per-source tolerances hold a bad source; the divergence check (JEG-460)
   flags a source that disagrees with the others too often.
2. **One definition per step** (JEG-556): seats, tiers, starter line, waiver
   line, flex. A parity test fails if two code paths disagree.
3. **Every value change** ships with a before/after table on live data, the
   Python reference, `value_check` at 0, the rank guard at 0, and a test that
   fails without the change.
4. **Every bug in a number** gets a row in `docs/risk-register.md` and a
   sentinel row in a fixture, so it cannot silently come back.
5. **No number is quoted in copy or a research post** until the ticket that
   fixes its inputs is live and the readout is re-run.

### Before changing the trade-value chart

Run the 12-combo headless sweep (3 scorings × 4 league sizes) against the built
`dist/`, and check `fixedPieIndexed` in `TradeValueCurveDiagnostics` for each.
Pie totals agreeing across sources proves nothing about curve shape: compare
where each position's curve starts. Since JEG-482 (2026-10-09), Indexed is one
order-preserving factor per chart and league setting, with no per-position
correction layer and no cap at 70. A published chart's curve starts where its
own values put it, and it must keep the publisher's ranking:
`pipelines/check_rank_guard.py` and `tests/test_rank_guard.py` must show zero
inversions. The ESPN, CBS ROS and Razzball lines also start where their own
projections put them. (`sourceScaleAgreement` was retired 2026-10-08, GAP-026:
publisher shape disagreement is the product.)

### Values explainer (DDF Value Logic, part of the dashboard)

Moved from a claude.ai artifact into the dashboard (Jeremy, 2026-10-25,
JEG-1086). `make sync` builds it to `dist/value-logic/index.html` (builder
`pipelines/build_values_explainer.py`, page template and engine extractor in
`app/values-explainer/`); How values work links to it. Every number is read
from the chart engine at the default setting (12 teams, Full PPR). It needs
Playwright: skipped with a notice locally, an error where
`RENDER_TESTS_REQUIRED=1`. Keep it current:

- After any change to value math (the files in `LOGIC_FILES` in the builder),
  update the narrative in `template.html` if the logic changed, then
  `make values-explainer MARK_REVIEWED=1` so the review section stops flagging
  it. The review banner and open math-review items sit in a collapsed section
  at the bottom.
- The old artifact (https://claude.ai/artifact/RALxprAWirGvjw8uwZwbfW) and its
  daily republish task stay until the dashboard page is verified live, then
  retire (Jeremy, 2026-10-25).

## Working efficiently (JEG-524)

- **Wait on CI and deploys with one blocking command:** `gh pr checks <n>
  --watch` or `gh run watch <id> --exit-status`. No `sleep`/`ps`/`until`
  polling loops.
- **Read by search or line range, not whole files.** Use `rg -n`, then read the
  lines you need. Never `cat` or fully re-read large files such as
  `app/v2/finder.js`, `app/v2/v2.js`, `pipelines/value_reference.py` or
  `docs/methodology.md`.
- **Screenshots:** one per check; don't re-read an image already taken.
- **Keep tool output short:** `tail`, `head`, `gh ... --jq`, `--json` with
  only the fields needed; write large results to a scratch file.
- **Delegating:** brief subagents from `docs/agent-brief-template.md` (it
  carries `Touches:`, `Model tier:` and the runnable Done-when block); link
  docs instead of pasting them. Keep tasks narrow, ask for one output shape
  (findings with file:line refs, options with a recommendation, a minimal
  patch, a trace, or a risk list), and say "do not edit files" for review-only
  work. Treat results as raw material: re-read touched files and run the gate.
  Don't delegate edits smaller than the brief. More: `docs/delegation-workflow.md`.

## Continuity

GitHub and Linear hold the state, never a chat thread. Switching sessions or
harnesses should cost about 10-20 minutes: start with `git status` and recent
commits; commit and push validated slices promptly; if a slice can't be
committed yet, leave a handoff (Linear comment or doc) with state, changed
files, commands run, failures and the next action. Don't leave decisions only
in chat.
