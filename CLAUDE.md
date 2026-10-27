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

Several Claude sessions work this repo at once: the back end, and the front end on the Windows PC, on the Mac and in the cloud, plus the hosted Claude Managed Agent. Linear decides who owns what.

- **Owner label.** Every ticket a session works carries exactly one label from the `Session` group: `session:be`, `session:fe-pc`, `session:fe-mac`, `session:fe-cloud` (front end running in the cloud; added by Jeremy, 2026-10-24, because that session is neither the PC nor the Mac one) or `session:cma` (the hosted Managed Agent: queue run every 2 hours, up to 3 non-overlapping tickets in parallel, merges on green gates; config and rules in `managed-agents/`, Jeremy 2026-10-27, JEG-1173). The label is the owner; the Linear assignee stays Jeremy.
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

  The `session:cma` managed agent has a standing takeover (Jeremy, 2026-10-27,
  JEG-1173: "You can take back any tickets assigned to other harnesses unless
  you can tell they have sessions actively moving forward"): it may take any
  Trade Value Chart ticket from another Session label, `muse` or `owner:*`
  that shows no comment, commit or PR update in the last 4 hours. A session
  that wants to keep a ticket keeps its heartbeat current.

  To take over:
  1. Comment `taking over from <session> · last heartbeat <time> · continuing from <branch>`.
  2. Swap the Session label.
  3. Continue from the backup branch.

  The previous owner, on returning, reads the comment and doesn't resume.
- **Idle hands.** A session with an empty queue may pick up another session's **Todo** tickets (not In Progress ones), oldest priority first. It swaps the label and comments `picked up by <session>`.
- **Handoff.** A session that is stopping comments on each of its In Progress tickets with its state and branch, then moves them back to Todo so another session can claim them.
- **Hot files.** One In Progress ticket per hot file (list in `AGENTS.md`); a ticket names its hot files under `Touches`.
- **Merge order.** Always rebase on `main` before pushing. The contract test (`tests/test_v2_contract_render.py`) and `make validate` must pass. The lead's per-PR merge checks are `runbooks/merging-prs.md`.
- **Decisions go to Jeremy as multiple choice.** Product, copy and method choices that are his are posted on the ticket as options with context and a recommendation; agents do not pick defaults (Jeremy, 2026-10-22, JEG-850: "Product/design choices that are Jeremy's go to him as multiple choice with context; do not pick defaults"). Pre-launch, block only on wrong numbers and finish end to end.

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
- **Every session that changes anything writes a log entry** in
  `docs/claude-log/YYYY-MM-DD-slug.md` (Jeremy, 2026-10-23, JEG-975: "1 - A").
  One file per PR, with "Verified (check named)" separate from "Claimed, not
  confirmed"; the format is in `docs/claude-log/README.md`. The commit message
  and PR description say the same in short.
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

## Values explainer (DDF Value Logic, part of the dashboard)

Moved from a claude.ai artifact into the dashboard (Jeremy, 2026-10-25, JEG-1086:
"Ddf value logic should migrate from a Claude artifact to part of the dashboard").
`make sync` builds it to `dist/value-logic/index.html` (builder
`pipelines/build_values_explainer.py`, page template and engine extractor in
`app/values-explainer/`); How values work links to it. Every number is read
from the chart engine at the default setting (12 teams, Full PPR). It needs
Playwright: skipped with a notice locally, an error where `RENDER_TESTS_REQUIRED=1`.
Keep it current:

- After any change to value math (the files in `LOGIC_FILES` in the builder),
  update the narrative in `template.html` if the logic changed, then
  `make values-explainer MARK_REVIEWED=1` so the review section stops flagging it.
  The review banner and open math-review items sit in a collapsed section at the bottom.
- The old artifact (https://claude.ai/artifact/RALxprAWirGvjw8uwZwbfW) and its daily
  republish task stay until the dashboard page is verified live, then retire (Jeremy, 2026-10-25).

## Usage: same quality, fewer tokens (JEG-524)

The general rules are in the user-level "Usage Discipline" section. For this repo
(these override it where they differ):

- **Rotate the lead thread at about 200k context** (or at each GO LIVE milestone).
  First write the handoff as a comment on the active Linear ticket (state, open
  PRs, next step, decisions pending), then tell Jeremy to start a new thread.
- **Wait on CI and deploys with one blocking command:** `gh pr checks <n> --watch`
  or `gh run watch <id> --exit-status`. No `sleep`/`ps`/`until` polling loops.
- **Read by search or line range, not whole files.** Use `rg -n` and then read
  the lines you need. Never `cat` or fully re-read large files such as
  `app/v2/finder.js`, `app/v2/v2.js`, `pipelines/value_reference.py` or
  `docs/methodology.md`.
- **Screenshots:** one per check, and do not re-read an image already taken.
- **Models:** `deep-worker` (Opus) only for T1 tickets (see the tiers in
  `AGENTS.md`); `worker` (Sonnet) for everything else. Brief subagents with
  `docs/agent-brief-template.md`; don't paste a long shared brief.
- **Keep tool output short:** `tail`, `head`, `gh ... --jq`, `--json` with
  only the fields needed; write large results to a scratch file.
- Read `AGENTS.md`, then only the docs your task needs.
  `docs/engineering-notes.md` holds the dated incident notes.
- **Direction questions still go to Jeremy directly** (AskUserQuestion is fine),
  but batch them into one ask and never repeat a question he has answered;
  check the ticket and memory first.
