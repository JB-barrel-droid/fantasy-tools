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

## Review and merge protocol (Jeremy, 2026-10-29)

Codex stopped at 19:12 UTC on 2026-10-29 (Jeremy: "I want to get off of Codex
I think, having you use a seperate reviewer makes sense. Codex is slowing us
down."). Claude sessions now do all review and merging (JEG-1218). The `codex`
label and Codex release notes in `HANDOFF.md` are history. This section wins
over older review or merge text in this file and in `HANDOFF.md`.

- **One independent review per PR.** It comes from a Claude session that did
  not write the PR. The author's own check doesn't count, and nobody reviews
  the same head twice (Jeremy, 2026-10-28). The review receipt names the exact
  head it passed. If the head changes after that, the new commits get a delta
  review only. A Codex pass on a PR's exact current head, made before the
  handover, counts as that PR's one review (Jeremy's pick A, 20:10 UTC).
  Label the risk: `review-light` (docs, copy), `review-standard` (features,
  UX, tests) or `review-high-risk` (value math, identity, persistence, shared
  context). Changes to this file, `CLAUDE.md` or permissions are never
  `review-exempt`.
- **Corrections.** A substantial review finding becomes one child ticket with
  the same owner, branch and PR. The owner acknowledges each finding and
  returns a corrected head with a test that fails before and passes after. A
  ticket is not done while a correction child is open. A small fix just moves
  the original ticket back to In Progress.
- **Branch rule.** Never push straight to `main` and never force-push. Push
  with an explicit branch refspec (`git push origin <branch>`) so an inherited
  upstream can't send a bare push to `main`. Claim on the ticket before
  touching a branch. While another owner still holds a branch, touch it only
  after 30 minutes with no push from them, or with their explicit OK, and then
  only to merge `origin/main` in normally: no rebase, no force push, no other
  edits. The owner pulls before their next push. Taking a ticket over is
  different (Takeover below). Never delete a branch, data, a file or work in
  progress without Jeremy's yes.
- **At most 8 PRs ready for review at once.** Keep the rest as drafts.
- **Merging.** A Claude merge session batches merges: at most 7 PRs of the same
  risk on pinned current main, with USO valuation work in its own batch. Each
  PR merges on its reviewed head, with green CI on that exact head and a clean
  merge onto current main. Engine PRs still go one at a time (Hot files below).
  Jeremy approves merges by PR number, and on 2026-10-29 at 21:08 UTC gave a
  standing OK: "merge anything you recommend once it is green". That covers a
  PR whose independent review passed, once its checks are green.
- **Still needs Jeremy's yes each time**, standing OK or not: any PR that
  changes value math (how values are computed) or a published value, whether
  or not it claims the published numbers move, with the before and after
  values shown to him first; every Supabase deploy, migration, production-data
  change or deletion (named each time); and every backend or edge-function
  deploy. The one exception is a routine data refresh on green gates, which
  changes inputs, not the math (Routing below).
- **Data rules that never bend:** "do not blend weekly data with ROS data,
  ever." (Jeremy, 2026-10-28). "Natural means both sides, not just 1 side"
  (Jeremy, 2026-10-28): a natural-fit trade has to fit both teams.

## Who does what

### Model tiers

The tier is the **minimum** model. Name it in the ticket or brief: the
`Model tier` label group was retired on 2026-10-28 (JEG-1211). Names rot, tiers don't. Pick the best
current model in the lane.

| Tier | Claude subscription | ChatGPT subscription | OpenRouter / MiniMax | Use for |
| -- | -- | -- | -- | -- |
| **T1 deep** | Opus / Fable, high effort (`deep-worker`) | top GPT / Codex, high reasoning | not allowed | Engine and value math, methodology, any bug with unknown root cause, design, final review of T2/T3 output, every merge and deploy |
| **T2 build** | Sonnet (`worker`) | Codex, medium | a strong open model (checked per task) | Implementation against a written spec: pullers, pipeline stages, migrations, FE built to a contract line, tests. Escalate to T1 after 2 failed gate runs |
| **T3 light** | Haiku | small GPT | cheap OpenRouter models (e.g. DeepSeek); **MiniMax M3 only** (Jeremy 2026-10-09: 2.5 is out) | Copy edits, doc moves, research sweeps, scraping and capture, triage, repo hygiene, first drafts |

The ChatGPT/Codex column is inactive since Codex stopped on 2026-10-29
(review and merge protocol above).

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
   T1: say so in its brief.
5. Reviews of T2/T3 work are T1, and are a different model from the author
   where possible.

### Routing

| Work type | Route |
| --- | --- |
| PM: Linear tickets and routing, headless coding runs (one per ticket), questions to Jeremy | Ba-Nana (Grok Bot), Jeremy 2026-10-26; see `HANDOFF.md` |
| Review, integration, merge/push/deploy, production QA, scheduled jobs | Claude sessions, T1, under the review and merge protocol above (Jeremy 2026-10-06, ops-ownership-001; 2026-10-29, JEG-1218) |
| Methodology, values, copy, destructive prod actions, outward-facing changes | Jeremy (except routine data refreshes on green gates, which change inputs, not value math) |

- **Cheap runs.** DeepSeek through OpenRouter, and MiniMax M3 until the plan
  ends about 2026-10-31, do tests, CSS, copy and small features (Jeremy,
  2026-10-26, in chat). This lifts "MiniMax is not used" (JEG-584, closed
  2026-10-12) for that window only. Rules 2 and 3 apply: draft PR, Claude review.
- **Muse (Roman)** works here only as a last resort when Jeremy asks (the
  `muse` label was retired on 2026-10-27; see `HANDOFF.md` "Working with
  Muse"). It works on `muse/jeg-<id>-<slug>` branches, merges main in (never
  rebases or force-pushes) and opens PRs for Claude review. Muse output is
  untrusted input until it passes the repo pipeline. Muse never
  resolves player identity, edits fixtures, triages `review_rows`, pushes to
  `main`, merges or closes PRs, or closes Linear issues.
- **MiniMax: M3 or newer only, for the managed agent's bulk work** (Jeremy,
  2026-10-27, JEG-1173: "open router and my minimax subscription"; "M3, or the
  more recent one Minimax added to the subscription"). Earlier rule (2026-10-09:
  "I only want to use M3 if we use it. 2.5 stinks.") still holds: never M2.5,
  never value math, output untrusted until the gate passes. The lanes/outbox
  dispatch protocol was archived 2026-10-07 (`archive/2026-10-07/lanes/`).
  `lanes/protocol.py` and `lanes/plan_status.py` stay only for existing tests.
- **Supabase first** for schedules, checks and orchestration (pg_cron, Edge
  Functions, the `monitoring` schema). GitHub Actions does the site build,
  deploy and repo tests; pg_cron schedules any job that must run in Actions.
- The lanes/outbox dispatch protocol is archived (`archive/2026-10-07/lanes/`);
  `lanes/protocol.py` and `lanes/plan_status.py` stay only for existing tests.

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
| Labels | one type (`Bug`, `Feature` or `Improvement`); `claude` once claimed; a review risk label once a PR is up. `needs-jeremy`, `blocked-dependency` and `ready-for-claude` when they apply. The `Session`, `Model tier`, `BE priority` and `needs-review` labels were retired on 2026-10-28. |
| Milestone | The current project milestone in Linear (M1 to M3 and M5 are complete; M4 Research tab is open). |
| Relations | `blocked by` for real ordering. Never rely on prose like "after 499". |

### Priority and status

* **Urgent**: live numbers are wrong, or deploy is broken. At most 3 open at once.
* **High**: on the critical path of the current milestone.
* **Medium**: next milestone.
* **Low**: parked. Nobody picks it up unless the queue is empty.

Backlog = not scheduled. Todo = in a session's queue. In Progress = an agent is
working it now and heartbeats. **In Review = waiting on an independent review
or on Jeremy**; a wait on Jeremy carries `needs-jeremy` and the question plus a
recommendation in a comment. Done = merged and live.

### Ownership and claims (updated 2026-10-29)

Several Claude sessions work this repo at once: cloud threads started from
Jeremy's Claude chat and sessions on the Mac. Linear decides who owns what.

- **Owner.** Claimed work carries the `claude` label; the Linear assignee stays
  Jeremy. The `Session` labels (`session:be`, `session:fe-pc`,
  `session:fe-mac`, `session:fe-cloud`, `session:cma`) were retired on
  2026-10-28. The hosted managed agent (`session:cma`) was retired by Jeremy
  on 2026-10-27 (JEG-1173): it has no queue and no standing takeover. `muse` and `owner:*` are retired too.
- **Queue (JEG-567).** The queue is the Todo tickets in Jegabee, by Linear
  priority, then oldest first. Backlog is not the queue: a ticket enters it when
  Jeremy moves it to Todo. The one exception is `ready-for-claude`, which marks
  audited, bounded Backlog work a session may move to Todo and claim once the
  Todo queue is worked. A Todo ticket whose domain is unclear gets
  `needs-jeremy` and a question in a comment instead of a guess.
- **Claim.** Before starting, a session checks the ticket's comments and open
  PRs for another owner, sets it In Progress, adds `claude`, and comments
  `taken by <session> · <UTC time> · branch <name>`, saying that Jeremy
  instructed it (Jeremy, 2026-10-29: "be sure to mark what you are picking
  up"). It removes `ready-for-claude` on claim. It doesn't start a ticket
  another session is moving without the branch rule above.
- **Heartbeat.** While a ticket is In Progress, the owner comments at least
  every 4 hours of active work, at every push, and when it parks the ticket:
  what's done, what's next, and the branch (`claude/<ticket>-<slug>`), pushed
  to GitHub at each heartbeat so work never lives on one machine only.
- **Takeover.** A session may take over a ticket that shows no comment, commit
  or PR update for 4 hours, when its owner gives an explicit OK, or when Jeremy
  says so. It comments `taking over from <session> · last heartbeat <time> ·
  continuing from <branch>`. Ownership moves with the takeover, so the taker
  then works the branch as its own: it keeps working on it, merges
  `origin/main` in normally, and never rebases or force-pushes. The previous
  owner, on returning, reads the comment and doesn't resume.
- **Handoff.** A session that is stopping comments on each of its In Progress
  tickets with its state and branch, then moves them back to Todo.

### Decisions go to Jeremy as multiple choice

Product, copy and method choices that are his are posted on the ticket as
options with context and a recommendation; agents do not pick defaults
(Jeremy, 2026-10-22, JEG-850). Add `needs-jeremy`, move the ticket to In
Review, and claim the next ticket rather than waiting. Batch questions and
never repeat one he has answered; check the ticket first. When he answers, the
owner quotes the decision with the date, removes `needs-jeremy`, and moves the
ticket back to Todo (or In Progress if it resumes now). A decision that changes
a rule also lands in `docs/decisions.md`. Pre-launch, block only on wrong
numbers and finish end to end.

Ticket descriptions are working notes, not the record. A finished fact goes in
`docs/` (indexed in `docs/README.md`) and is linked from the ticket.

## Hot files and merging

**Hot files** (one In Progress ticket at a time): `app/v2/v2.js`,
`curve-widget.js`, `value-model.js`, `value_reference.py` (and its spec
reference), `config/roster.json`, `config/lineup_parameters.json`,
`pipelines/bake_players.py`.

**Merge protocol** (the Claude merge session, on Jeremy's approval as in the
review and merge protocol above):

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
`app/values-explainer/`); How values work shows it inline in a same-origin frame (JEG-1107: Jeremy, 2026-10-25, "ensure this is part of the main dashboard, not some seperate dashboard"), and the bare `value-logic/` URL redirects into that tab. Every number is read
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
