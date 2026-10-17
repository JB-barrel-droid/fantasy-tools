# Working agreements for AI sessions in this repo

Read this first. It is short on purpose. Every durable doc is listed in `docs/README.md` (the index); runbooks for recurring jobs are in `runbooks/README.md`.

## Pre-launch: ship, and keep the numbers honest

Jeremy, 2026-10-07: no users yet, and one owner (Claude) writes, reviews and
merges, so the late-September multi-agent policing is retired. Get fresh data
live every week, protect only what keeps the numbers honest, refine methodology
after launch.

The live plan is Linear ticket **JEG-440 (GO LIVE)**; Linear is the source of
truth. In Progress means an agent is working it now; Done means merged and
live. Parallel work is uncapped (Jeremy, 2026-10-09), limited only by: no two
agents on one code path, value changes paired with the Python reference on one
branch, merges ordered so main stays green.

## Linear (team Jegabee, project Trade Value Chart)

Follow the user-level Linear rules (ticket per workstream, status comments,
quoted decisions, agents naming their ticket, "(part of JEG-xxx)" PR titles).

- The back end owns tickets for pipelines, Supabase, engine math and
  workflows. The v2 front-end session owns its own tickets.
- Front-end requests that need engine or data changes become back-end
  tickets, linked to the front-end ticket.
- Fidelity findings from the pulse, an audit or a reviewer get a ticket
  (Urgent if live numbers are wrong) and a row in `docs/risk-register.md`.

### Session ownership and takeover (Jeremy, 2026-10-10)

Several Claude sessions work this repo at once: the back end, and the front end on the Windows PC and on the Mac. Linear decides who owns what.

- **Owner label.** Every ticket a session works carries exactly one label from the `Session` group: `session:be`, `session:fe-pc` or `session:fe-mac`. The label is the owner; the Linear assignee stays Jeremy.
- **Queue (JEG-567).** A session's queue is the Todo tickets in Jegabee that carry its own Session label. Backlog is not the queue: a ticket enters it when Jeremy moves it to Todo. At session start, and each time a ticket closes, the session reads its queue and claims the top ticket:
  - back end: by the `BE priority` label (Now, Next, Then, Later), then Linear priority;
  - front end: by Linear priority, then oldest first.
- **Unrouted tickets.** A Todo ticket with no Session label has no owner yet. A session whose queue is empty routes the ones that are clearly its domain (engine, pipelines, data and research math go to `session:be`; pages and copy to a front-end session): it adds its label, comments `routed to <session>`, and works its queue. If the domain is unclear, it adds `needs-review` and asks Jeremy in a comment instead of guessing.
- **Blocked on Jeremy.** When a ticket needs his decision, the session comments the question with the options and its recommendation, adds `needs-review`, moves the ticket to In Review, and claims its next ticket rather than waiting. Once Jeremy answers on the ticket, the owner quotes the decision with the date, removes `needs-review`, and moves the ticket back to Todo (or In Progress if it resumes now). In Progress stays reserved for work an agent is doing.
- **Claim.** Before starting, a session:
  1. sets the ticket In Progress;
  2. checks that the `Session` label is its own and that the ticket carries one `Model tier` label (T1 deep, T2 build, T3 light; table in `AGENTS.md`);
  3. comments `taken by <session> · <UTC time> · branch <name>`.

  It doesn't start a ticket that carries another session's label without a takeover.
- **Heartbeat.** While a ticket is In Progress, the owner comments at least every 4 hours of active work, at every push, and when it parks the ticket. Each comment states what's done, what's next, and the backup branch (`fe/<ticket>` or `be/<ticket>`). The owner pushes that branch to GitHub at each heartbeat, so work never lives on one machine only.
- **Lag and takeover.** Another session may take over a ticket when:
  - it is In Progress with no heartbeat or commit for 4 hours; or
  - its owner session is offline or idle, and the taker's own queue is empty; or
  - Jeremy says so.

  To take over:
  1. Comment `taking over from <session> · last heartbeat <time> · continuing from <branch>`.
  2. Swap the Session label.
  3. Continue from the backup branch.

  The previous owner, on returning, reads the comment and doesn't resume.
- **Idle hands.** A session with an empty queue may pick up another session's **Todo** tickets (not In Progress ones), oldest priority first. It swaps the label and comments `picked up by <session>`.
- **Handoff.** A session that is stopping comments on each of its In Progress tickets with its state and branch, then moves them back to Todo so another session can claim them.
- **Hot files.** One In Progress ticket per hot file (list in `AGENTS.md`); a ticket names its hot files under `Touches`.
- **Merge order.** Always rebase on `main` before pushing. The contract test (`tests/test_v2_contract_render.py`) and `make validate` must pass.

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
  are warnings: label them on the page and don't stop the site.
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
- **The commit message and PR description are the record.** Say what you
  verified (name the check) separately from what you assumed. No separate
  session log is required; `docs/claude-log/` is kept as history.
- **`make sync` is the single publish path** and stamps the build tag. Do not
  re-add `dist/static`, `dist/server`, `space.json` or `deploy.sh`.
- **Do not touch `~/Projects/"fantasy tools"`** on the user's machine beyond the
  `Claude outputs/` folder. It holds `data/raw` (33MB, gitignored), the only
  copy of the player-news pipeline's inputs.
- **Muse owns nothing here.** Claude owns merges, deploys, QA and schedules.
  Schedules run from Supabase pg_cron; GitHub Actions does the build and deploy.

## Before changing the trade-value chart

Run the 12-combo headless sweep (3 scorings × 4 league sizes) against the built
`dist/`, and check `fixedPieIndexed` in `TradeValueCurveDiagnostics` for each.
Pie totals agreeing across sources proves nothing about curve shape: compare
where each position's curve starts. Since JEG-482 (2026-10-09), Indexed is one
order-preserving factor per chart and league setting, with no per-position
correction layer and no cap at 70. A published chart's curve therefore starts
where its own values put it, and it must keep the publisher's ranking:
`pipelines/check_rank_guard.py` and `tests/test_rank_guard.py` must show zero
inversions. The ESPN, CBS ROS and Razzball lines also start where their own
projections put them. (`sourceScaleAgreement`, the peak-vs-anchor
band on published charts, was retired 2026-10-08, GAP-026: publisher shape
disagreement is the product.)

## Values explainer (living artifact)

Jeremy reads how every source's values are made at the claude.ai artifact
https://claude.ai/artifact/RALxprAWirGvjw8uwZwbfW ("DDF Value Logic"). It is
built by `make values-explainer` (`pipelines/build_values_explainer.py`, page
template and engine extractor in `app/values-explainer/`) into
`output/values-explainer/index.html`, and every number on it is read from the
chart engine. Keep it current:

- After any change to value math (the files in `LOGIC_FILES` in the builder),
  rebuild and republish to that URL in the same session. If the logic changed,
  update the narrative in `template.html` to match, then
  `make values-explainer MARK_REVIEWED=1` so the page stops flagging it.
- A daily scheduled task rebuilds and republishes it from `main`. When the page
  says "Logic changed since this explanation was reviewed", the narrative is
  stale: fix the text, not the numbers.

## Usage: same quality, fewer tokens (JEG-524)

The general rules are in the user-level "Usage Discipline" section. For this repo:

- Subagents: `worker` (Sonnet) for routine lanes, `deep-worker` (Opus) for value
  or engine math, unknown-root-cause debugging, design and final review. Brief
  them with `docs/agent-brief-template.md`; don't paste a long shared brief.
- Read `AGENTS.md`, then only the docs your task needs.
  `docs/engineering-notes.md` holds the dated incident notes.
- The lead session rotates at each GO LIVE milestone, or once context passes
  about 150k tokens. Before telling Jeremy to start a new thread, post the
  handoff as a comment on the active Linear ticket.
