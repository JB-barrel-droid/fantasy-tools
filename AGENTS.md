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

## Two-agent protocol

Confirmed by Jeremy on 2026-10-28 (America/Chicago), with explicit updates on
2026-10-29 through 18:08 UTC, JEG-1218. This section
supersedes older instructions below wherever they conflict with this protocol,
including overlap, review, release and approval rules. Unrelated requirements still
apply. Current release boundaries are recorded in `HANDOFF.md`.

### Agents and split of work

- Codex and Claude both have access to GitHub, Supabase, the DDF connector and
  the Flaim Fantasy connector, and either can test the live connector.
- **Codex is the single release coordinator.** Codex owns integration, all merges
  to main, `HANDOFF.md`, and focused independent review of Claude's work.
- Per Jeremy's subsequent capacity direction, shift more implementation and
  testing to Claude on explicitly claimed tickets with bounded scope and clear
  acceptance criteria. Claude may own front-end features, scoped connector
  work, refactors, test and CI fixes, and backlog implementation, in addition to
  explainer/UX copy, source and data research (FantasyCalc, projection sources,
  source freshness), ambiguous bug investigation (including connector bugs),
  and writing and triaging Linear tickets.
- This broadens the earlier research/copy-oriented split for future assigned
  work, not active branch ownership. Existing owners and branches remain
  grandfathered; do not take over their work without the claiming/handoff
  procedure. All approval, independent-review and release gates below remain
  unchanged; Codex-authored work still needs a separate independent reviewer.

### Claiming and handoff

- Codex tickets carry a `codex` label or Linear agent assignment. Claude tickets
  carry a `claude` label. Create both labels in Jegabee if missing.
- Before claiming, check both agent labels, native assignee/delegate, comments,
  open PRs/branches, parent/child scope, acceptance criteria and explicit holds.
  A missing label or blocker relation does not prove that work is unclaimed or ready.
- Claim with a ticket comment naming worker, branch, exact files, bounded
  deliverable and dependencies, then recheck for a simultaneous claim. Resolve
  conflicts before editing; mark In Progress only when work actually starts.
- Only one agent works a ticket at a time. To hand off, comment with current
  state, PR link and next step, then swap the label.
- Keep a ready Claude queue larger than Claude can work concurrently so it does
  not wait for Codex to assign the next task. Queue future work in Backlog or
  Todo, not In Progress; active ownership and release boundaries still apply.
- `ready-for-claude` means audited, approved, bounded and unclaimed. After
  exhausting actionable active/Todo work, including review corrections, Claude
  may promote only such ready-labeled Backlog work to Todo and claim it. Recheck
  ownership/races without repeating an unchanged substantive readiness audit.
  Remove readiness immediately on claim, block or handback. Unknown readiness
  stays Backlog. Name dependencies and use actual blocker relations where
  appropriate (`blocked-dependency`); use `needs-jeremy` for decision/approval
  holds. Independent scaffold/module/test children can proceed inside their
  explicit boundary while parent live integration is held; do not count both twice.
- Substantial review corrections use a bounded child ticket linked to the SAME
  existing PR/branch. Small fixes return the original ticket to In Progress.
  Both require an explicit corrective claim and owner acknowledgment; never
  duplicate a live corrective worker. Hand back the corrected exact head/tests.

### Branches and overlap

- New work uses `codex/JEG-###-slug` or `claude/JEG-###-slug`.
- Existing branches and owners are grandfathered. Do not rename or transfer
  active branches during the release queue.
- Never push directly to main or force-push. Use an explicit branch push
  refspec so an inherited upstream cannot send a bare push to main.
- Before any normal main-only merge into another agent's branch, post a ticket
  claim. Then either verify that its owner pushed nothing in the preceding
  30 minutes or obtain the owner's OK. Make no other edits under
  this exception. Coordinate concurrent writes; the owner pulls before its next
  push. Other changes require the normal ownership/corrective handoff.
- Never delete a branch, data, file or work in progress without Jeremy's yes.
  Automatic branch cleanup also needs specific approval; retain branches otherwise.
- File overlap triggers coordination, not an automatic stop. Independent
  changes can proceed on separate branches. When changes conflict, serialize
  integration and retest against the merged result.

### Review and release

- Use `review-light` for bounded low-risk copy/docs, `review-standard` for
  ordinary features/UX/tests, and `review-high-risk` for calculations, identity,
  persistence/provenance, shared context and similarly sensitive behavior.
- One independent reviewer pass is sufficient; the author's self-check does
  not count and the coordinator does not repeat the same review. A separate
  automated review can count. After corrections, review only material changed
  code and affected integration; reuse unchanged evidence.
- `review-passed` records the receipt's exact head and scope. It means release
  preflight, not Done or permission to ship; a material unreviewed delta needs
  its own review. Labels never create a synthetic approving GitHub review.
- Pure docs-only typos, formatting and status notes can be `review-exempt`
  after scope verification. This excludes AGENTS/protocol/permission changes,
  substantive architecture or calculation/methodology claims, behavior, tests
  and deployment configuration. This protocol change requires independent review.
- Only release work Jeremy asked for. Codex prepares each batch on pinned
  current main, with at most seven PRs of the SAME risk class. USO valuation
  stays in its own batch. Run combined required CI once on that exact batch
  head and obtain one integration review of conflicts and changed code only.
  Do not repeat unchanged constituent reviews or waive required CI.
- Main must be green and fresh immediately before merge. If main moves,
  normally integrate current main and rerun required CI on the resulting head;
  there is no generated-data-only moving-main exemption. Apply the branch
  claim/30-minute-or-owner-OK rule before cross-agent integration.
- Squash-merge the reviewed release PR, then wait for exact-SHA publication.
  Docs/tests batches need the exact-SHA publish check plus the synthetic check
  before the next batch. Bench values, JSN discovery, pricing context and large
  UI changes require their named browser journey first. Other feature batches
  verify their live acceptance and affected regressions before the next batch.
- A failed live check stops the next batch and requires reverting the WHOLE
  batch through a revert PR, never a direct main change. Supabase and deletion
  permissions remain separate and unchanged. Routine Linear updates, research
  drafts and private preview preparation need no release review to begin.

### Jeremy's approvals

- Jeremy approves new calculation logic, defaults, ranking rules and design
  direction.
- Once he approves a specific change, implementation within that scope proceeds
  through these release gates without asking again. Material deviations go
  back to him.
- Every Supabase change, including each deployment, migration or production-data
  change, needs his fresh approval naming the function or PR, every time.

### Records and standing rules

- Linear records ownership and acceptance criteria. GitHub records code, review
  and test evidence. `HANDOFF.md` records current status and next steps.
- Claude leaves handoff notes in tickets and PRs. Codex maintains `HANDOFF.md`.
- Support Standard, Half PPR and PPR. Label data as published, previous-season,
  modeled, stale or unavailable; never present 2026 data as 2027.
- Never blend weekly and rest-of-season data. Natural fit means BOTH teams,
  not one side; new fit mathematics still needs Jeremy's approval.
- JEG-1217 is Claude-owned implementation in the existing dashboard first;
  a simpler experience follows working features. This grants no new numerical
  ranking, default, design or methodology authority.

## Pre-launch: ship, and keep the numbers honest

Jeremy, 2026-10-07: no users yet, and the late-September multi-agent policing
is retired. Get fresh data live every week, protect only what keeps the numbers
honest, refine methodology after launch. Linear is the source of truth.
Parallel work is uncapped (Jeremy, 2026-10-09). Coordinate overlapping files
and serialize conflicting hunks; pair value changes with the Python reference
on one branch and order releases so main stays green.

## Who does what

### Model capability guidance (legacy tier names)

Choose capability from the scope using the tier guidance below; do not recreate
retired Model-tier labels as mandatory ownership gates. Names rot, tiers don't.
Pick the best current model in the lane.

| Tier | Claude subscription | ChatGPT subscription | OpenRouter / MiniMax | Use for |
| -- | -- | -- | -- | -- |
| **T1 deep** | Opus / Fable, high effort (`deep-worker`) | top GPT / Codex, high reasoning | not allowed | Engine and value math, methodology, any bug with unknown root cause, design, final review of T2/T3 output, every merge and deploy |
| **T2 build** | Sonnet (`worker`) | Codex, medium | a strong open model (checked per task) | Implementation against a written spec: pullers, pipeline stages, migrations, FE built to a contract line, tests. Escalate to T1 after 2 failed gate runs |
| **T3 light** | Haiku | small GPT | cheap OpenRouter models (e.g. DeepSeek); **MiniMax M3 only** (Jeremy 2026-10-09: 2.5 is out) | Copy edits, doc moves, research sweeps, scraping and capture, triage, repo hygiene, first drafts |

Rules:

1. **Designing or deriving value math is T1.** Anything that decides a
   published value, a curve, a tier, or a waiver line. Executing an approved
   spec (a config switch, porting a rule to a second path, a fixture refresh)
   is T2 with a T1 review at merge. A bug whose root cause is unknown is T1
   until the cause is named.
2. **Codex coordinates merges.** Other implementation workers return a draft
   PR for the independent review and release gates above. Existing branch
   names remain valid; new work follows the two-agent branch convention.
3. **T3 output is untrusted** until the gate passes. T3 never resolves player
   identity, edits fixtures, or touches `config/` values.
4. A task described as T2 that needs a judgement call on the numbers needs T1
   capability: correct its brief and routing.
5. Reviews of T2/T3 work are T1, and are a different model from the author
   where possible.

### Routing

| Work type | Route |
| --- | --- |
| PM: Linear tickets, bounded work and questions to Jeremy | Codex coordinates; Claude may claim approved ready work. Ba-Nana's earlier role is historical; see `HANDOFF.md`. |
| Independent review, integration, releases and production QA | Codex coordinates under the two-agent protocol; an independent reviewer checks Codex-authored work. Earlier Claude-only release routing is retired. |
| Methodology, values, copy, destructive prod actions, outward-facing changes | Jeremy (except routine data refreshes on green gates) |

- **Cheap runs.** DeepSeek through OpenRouter, and MiniMax M3 until the plan
  ends about 2026-10-31, do tests, CSS, copy and small features (Jeremy,
  2026-10-26, in chat). This lifts "MiniMax is not used" (JEG-584, closed
  2026-10-12) for that window only. Rules 2 and 3 apply: draft PR, independent review.
- **Muse (Roman)** owns only Linear tickets labeled `muse` (Jeremy,
  2026-10-26; one owner per ticket, see `HANDOFF.md` "Working with Muse").
  On those it works on `muse/jeg-<id>-<slug>` branches, merges main in (never
  rebases or force-pushes) and opens PRs for independent review. Otherwise Muse
  works here only as a last resort when Jeremy asks. Muse output is untrusted
  input until it passes the repo pipeline. Muse never
  resolves player identity, edits fixtures, triages `review_rows`, pushes to
  `main`, merges or closes PRs, or closes Linear issues.
- **MiniMax: M3 or newer only.** The managed agent is retired (JEG-1173);
  this model constraint still applies to any approved MiniMax use (Jeremy,
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

- Route pipelines, engine/data and UI work to bounded domain tickets with
  explicit Codex/Claude ownership. Link dependent backend work instead of
  assuming a front-end owner can change math or deploy Supabase.
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
| Touches | Exact files/hunks and shared-file coordination; serialize conflicting edits. |
| Labels | `codex` or `claude` ownership/agent assignment and relevant readiness/review state. Legacy Session/Model-tier/BE-priority labels are not mandatory ownership gates. |
| Milestone | The current project milestone in Linear (M1 to M3 and M5 are complete; M4 Research tab is open). |
| Relations | `blocked by` for real ordering. Never rely on prose like "after 499". |

### Priority and status

* **Urgent**: live numbers are wrong, or deploy is broken. At most 3 open at once.
* **High**: on the critical path of the current milestone.
* **Medium**: next milestone.
* **Low**: parked. Nobody picks it up unless the queue is empty.
* Use Linear priority, named dependencies and the coordinator's current release
  order. Legacy BE-priority tags are not required and are not recreated.

Backlog = not scheduled. Todo = in a session's queue. In Progress = an agent is
working it now and heartbeats. In Review names the awaited independent review,
correction or Jeremy decision; mark explicit decision holds `needs-jeremy` with
the question and recommendation. `review-passed` goes to release preflight.
Done = merged and live, with the applicable risk-based verification.

### Ownership and queue operation (updated 2026-10-29)

The old `session:be`, `session:fe-pc`, `session:fe-mac` and `session:fe-cloud`
labels describe historical execution locations, not mandatory current ownership.
Use the two-agent claim, readiness and handoff rules above, checking native
assignments/delegates as well as labels. Preserve existing active owners.
The hosted Claude Managed Agent (`session:cma`) was retired by Jeremy on
2026-10-27 (JEG-1173): assign nothing to its queue. Its former four-hour
standing takeover is ended; it takes over nothing.

- **Queue:** work actionable active/Todo assignments first. Backlog self-service
  is limited to audited `ready-for-claude` work under the rules above; an empty
  personal queue does not authorize stealing another owner's Todo or active work.
- **Claim:** record worker, branch, exact files/hunks, deliverable and dependencies;
  reread for races before editing. Owner reassignment requires an explicit
  coordinated handoff or Jeremy's direction. Silence or four-hour inactivity
  alone does not transfer ownership.
- **Heartbeat:** on each push, every four active hours and when parking, record
  what is done, exact head/tests, next action and remote backup branch. Push
  validated slices explicitly so work does not live on one machine only.
- **Handoff:** record state, PR/branch and exact next step, remove readiness,
  and coordinate the new owner/status. Only genuinely independent audited work
  proceeds while a named dependency or decision holds the remaining part.

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

**Shared files requiring hunk coordination:** `app/v2/v2.js`,
`curve-widget.js`, `value-model.js`, `value_reference.py` (and its spec
reference), `config/roster.json`, `config/lineup_parameters.json`,
`pipelines/bake_players.py`.

Sharing a file is not a blanket prohibition: independent hunks may proceed on
separate branches; serialize conflicting edits and verify their integrated result.

**Merge protocol** (Codex coordinates):

1. Use the approved same-risk batch limit (at most seven), pinned current main,
   combined CI once and focused integration review above. Keep USO valuation
   separate. Historical curve-widget collisions are why conflicting hunks and
   engine/reference parity must be checked in the integrated result.
2. Bring the branch up to date by merging `origin/main` into it. Never
   rebase, never force-push (Jeremy, 2026-10-26). Cross-agent main-only merges
   require the ticket claim and 30-minute inactivity or owner OK above. Then `make validate`
   and the contract test (`tests/test_v2_contract_render.py`). Value changes
   pair JS, Python reference and spec reference on one branch with
   `value_check compare` at 0 and zero rank-guard inversions.
3. Squash-merge as "(JEG-xxx)". Wait for exact-SHA Deploy dashboard and perform
   the applicable synthetic/named-browser live gate before the next batch.
4. Use the required CI matrix for heavy suites (render, contract, 12-combo
   sweep); avoid duplicating the same heavy validation across local machines
   and CI. Run local heavy checks sequentially on the designated machine.
5. Order across lanes: back end engine, then front end that depends on it,
   then copy.
6. The per-PR checks (bot report matches head, `v2-render` green, mergeable,
   the preview run's `make validate` step read, no generated churn, stacked
   order, nav tab count) are in `runbooks/merging-prs.md`.

## Standing constraints

- **Finish end to end.** For a fix, refresh or deploy repair: commit, merge to
  `main`, wait for GitHub Actions, and check the live site when published
  output changes. Stop only if Jeremy says not to publish, the change needs a
  force push or history rewrite, or a separate required approval (including
  every Supabase change or deletion) is missing. Report the exact gate; retain
  branches when cleanup is unapproved.
- **Block only on the data math.** `make validate` is the deploy gate. It runs
  the build plus `make test-core`: curve shapes and starts, missing values
  never shown as zero, source integrity, and the published surfaces the page
  needs. The separate full suite (`make test-unit`) does not
  block. Staleness, review holds, coverage drift, import health and monitoring
  are warnings: label them on the page and don't stop the site. For narrower
  work, run the smallest meaningful command first, then `make validate`.
  These warning-only rules do not waive ownership, review or approval gates.
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
