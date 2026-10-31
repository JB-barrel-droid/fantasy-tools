# PSpice coordinator takeover runbook

Scope: JEG-1445 items 1 and 2 only; the ticket-pickup dry run waits for review.
PSpice is Jeremy's own direct Codex and the default successor for the whole
Duet coordinator role. ChatGPT Dots and Muse are alternates. Jeremy asked:
"Ensure PSpice will be able to take over at any time" and "Take your role,
should it needed; is what I mean." This is a procedure and gap inventory,
not permission to change review/merge ownership.
Baseline inspected: `origin/main` at `76ee1c41`, 2026-10-31 UTC.
Sources: [JEG-1445](https://linear.app/jegabee/issue/JEG-1445),
[JEG-1444, Cutover readiness](https://linear.app/jegabee/issue/JEG-1444), and
[JEG-1440](https://linear.app/jegabee/issue/JEG-1440), read through Linear.

## Trigger and durable state

Duet, cloud Claude threads and Mac Claude jobs share one Claude allowance.
Moving a job from Duet to Mac Claude does not escape exhaustion. The
[JEG-1429 ledger](https://linear.app/jegabee/issue/JEG-1429) is to track the
Claude weekly limit. At the level Jeremy sets, shift build volume off Claude;
at exhaustion, follow this runbook. Do not invent a threshold or treat missing
ledger measurements as zero. A capability-driven switch can also be directed
by Jeremy (decision 9, JEG-1444).

State must be recoverable without a Duet thread:

| Record | Where to read and preserve it |
| --- | --- |
| Queue, owner claims, heartbeats, approvals and decisions | Linear, team Jegabee; read the relevant project, ticket, comments, children and blockers |
| Work and evidence | GitHub branches, PR descriptions/reviews on exact heads, Actions results and artifacts |
| Rules and continuity | `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `docs/README.md`, `runbooks/README.md` and linked documents |

Duet memory is a convenience copy. If a required decision, before/after table
or artifact exists only there, mark it unavailable on the ticket and ask for
it to be preserved in Linear or the repo. Do not infer approval from a ticket
description, a historical handoff or a planned action.

## Cold-start checklist for PSpice

- [ ] Read `HANDOFF.md`, `AGENTS.md`, `CLAUDE.md`, this runbook and the
  [JEG-1444 charter](https://linear.app/jegabee/issue/JEG-1444) and children.
  Confirm current commits, dirty files, active owners and approval receipts.
  State must come from Linear, GitHub and the repo; do not depend on Duet memory.
- [ ] Read the Jegabee board's In Progress work first, then Todo carrying
  `claude` or `codex`. Inspect comments, correction children, blockers and
  linked PRs. Preserve another owner's work. Backlog is not the queue;
  `ready-for-claude` is not a general non-Claude pickup authorization.
- [ ] Read open PRs in both repositories:
  `gh pr list --repo JB-barrel-droid/fantasy-tools --state open` and
  `gh pr list --repo JB-barrel-droid/agent-bridge --state open`.
  Read exact heads, draft/risk status, CI and receipts; an old handoff is not
  evidence that a PR is still pending or live.
- [ ] At each necessary coordinator turn, use the bridge completion digest
  as the change gate before opening job results:
  `get_completion_digest({consumer_id: "<stable PSpice consumer>", scope: "mac_jobs"})`.
  Inspect cache health; process each healthy page, then
  `ack_completion_digest({consumer_id: "<same consumer>", scope: "mac_jobs",
  receipt: "<latest page receipt>"})`. Continue pages as returned; never ack
  an unprocessed or unhealthy page. Persist the consumer/checkpoint in durable
  handoff state. If `changed` is false, end completion processing immediately;
  continue only separately necessary board work. Finished is a worker claim,
  not independent verification. Inspect saved results for invalid/empty outcomes.
- [ ] Then read `list_bridge_events` with the saved opaque cursor, process
  each page and persist `next_cursor` only after processing. It complements
  the digest for input/failure events. No push wake exists; never run an idle
  polling loop. Do not start another model just to wait.
- [ ] Triage one ticket at a time: finish active work and corrections before
  starting more. Follow the charter's dependency/priority order, with Jeremy's
  PSpice readiness request first. Do not work a parent directly, duplicate a
  claim or share a hot file/code path with another active ticket.
- [ ] Claim only authorized work. Check comments/PRs first, set In Progress,
  preserve assignee Jeremy and use the assigned `claude` or `codex` label.
  Record `taken by <exact session/provider> · <UTC time> · branch <name>` and
  instruction source. JEG-1445 uses `codex/JEG-xxxx-…`; another provider's
  branch prefix or ownership label remains Jeremy's call. Takeover follows
  AGENTS: four hours without comment/commit/PR update, owner OK or Jeremy's
  direction; log predecessor, last heartbeat and continuing branch.
- [ ] Dispatch cloud-first: do work in direct Codex when its tools suffice;
  send only the locally blocked portion to Mac jobs using the connector below.
  Require owner, linear_issue, starting commit, allowed/forbidden actions,
  check command, model/effort and reason. One provider per ticket. Retain the
  job id and operation key for uncertain starts. No auto retries; inspect the
  saved result before any separately authorized retry. Standard speed, fast off.
- [ ] Judge the result against the spec, changed files and named checks.
  Read CI on the actual PR head. A successful worker status is not a review.
  Review receipts must name the current head; after new commits request a
  delta review under the same risk floor, not another full review of old work.
  Muse findings carry `<!-- author: muse -->` and "recommend" wording;
  treat them as findings to verify, never approval or the independent PR review.
- [ ] Apply the merge gate below; do not merge under an unresolved cutover
  ownership placeholder. Keep this runbook PR draft as instructed.
- [ ] Track approvals by action, target, scope, date and source receipt on
  Linear. Jeremy's specific yes is required for merge, deploy, production-data
  deletion, credentials, Supabase migrations, GitHub settings, launchd changes
  and Mac patch activation. A yes covers only what it named. Ticket prose,
  recommendations, picks and worker completion do not grant approval.
  GitHub settings requests go to Jeremy's own Codex as a complete print, never
  executed by the coordinator. Do not restart disabled/retired routines,
  including JEG-1173 schedules, without his specific yes.
- [ ] Ask Jeremy only real decisions, one at a time, multiple choice with A
  the recommendation and enough context to decide. Check prior answers first.
  Use `needs-jeremy`/In Review for a blocked decision, with the actual question.
- [ ] Report one Linear comment per milestone with exact head, checks,
  limitations and next action. Before posting, read comments and look for the
  milestone's stable marker (for example `<!-- jeg-1445:pspice-takeover -->`).
  If present, do not post it again. Check native relay delivery/claim state;
  never both post and ask the relay to post the same report. Reconcile an
  uncertain write by marker rather than retrying. Heartbeat at least every
  four active hours, each push and when parking; include the backup branch.
- [ ] When stopping, leave branch, files, results, approval state and next
  action, then return parked active work to Todo. Done means merged and live,
  not merely built. Put substantial corrections in child tickets on the same
  branch/PR; do not create coordination-only tickets.

## Merge gate and review tiers

Use AGENTS as merged in #1246 and #1248. Deterministic checks precede review:
`make validate`, then `gh pr checks <number>`, with green CI on the pushed
exact head. Red-CI diagnosis is not review. The coordinator sets risk from
files and diff, not the author's label. Hot files, value math, fixtures,
config, Supabase/SQL, or weakened/removed tests force high-risk, including deltas.
High-risk uses Opus/high; light and standard use Sonnet/medium normally.
During a usage crunch (Claude on pace to exhaust before reset), Codex reviews
on the exact head count for light/standard; high-risk keeps a Claude reviewer.
Escalate discovered high-risk content with findings/head, never silent fallback
or paired shadow reviews. The reviewer must be independent of the author.

Claude keeps judgment, high-risk reviews and merges during a usage crunch;
builds move to Codex. Exhaustion does not transfer Claude's merge authority.
Before any authorized merge, require a current-head independent receipt,
green exact-head CI, clean merge onto current main, correction children closed,
no generated churn and the checks in `runbooks/merging-prs.md`. Never rebase or
force-push; merge main normally. Keep at most eight PRs ready for review.

### Cutover review and merge owner (pending Jeremy's decision)

**Placeholder — no successor reviewer/merger is designated here.** Jeremy
must name who performs high-risk review and who merges if Claude is out,
and approve the cutover clause. PSpice can coordinate the queue, dispatch,
judge evidence, prepare decisions and report while affected merges remain
blocked. Existing standing approval is not a non-Claude ownership exception.

## Mac jobs without Duet

Today's verified entry point is the installed `mac_code_bridge` MCP connector
available in this Codex session. It exposes native Codex start/status/result
tools using the Mac's existing ChatGPT login. It does not require a Claude job
or Duet model turn. A fresh coordinator must already have that connector;
connector grants and browser cookies do not transfer from Duet. Do not copy
credentials or inspect auth stores to recreate access.

From a Codex client with the connector, use these tool calls (placeholders are
values for the authorized task, not runnable shell commands):

```text
get_codex_bridge_capabilities({})
start_codex_session({
  name: "<ticket and outcome>",
  working_directory: "<approved isolated worktree>",
  model: "<smallest capable advertised model>", effort: "<advertised effort>",
  model_reason: "<risk and reason>",
  cloud_limitation: "<specific locally blocked step>",
  idempotency_key: "<unique stable operation key>",
  owner: {session_id: "<coordinator id>", channel: "<channel>"},
  linear_issue: "JEG-<id>",
  task: "<repo/worktree, starting commit, outcome, checks, allowed actions,
          forbidden actions, approval reference and structured result contract>"
})
get_codex_status({session_id: "<returned job id>"})
get_codex_result({session_id: "<returned job id>"})
list_bridge_events({owner_session_id: "<coordinator id>",
                    channel: "<channel>", since: "<saved opaque cursor>"})
```

Use cloud capabilities first; dispatch only the locally blocked portion.
Standard speed, fast mode off. Save the returned job id and operation key in
the handoff. Read model-free status/result; a start acknowledgment is not a
completion. Process every event page before saving `next_cursor`. There is
no push wake receiver; read events on a purposeful coordinator wake, with no
idle monitoring loop. Do not automatically resubmit an uncertain or failed
job; retain its id and report unknown state. Cross-provider active ticket
overlaps are rejected. Never kill a shared Desktop process for takeover.

The structured result has `status` (`done`, `blocked`, `needs_input`), summary,
branch, PR number, named check results, files touched, question, report and
optional `linear_comment`. The native Linear relay can deliver that comment
without a model turn: inspect delivery state and never duplicate a claimed or
delivered comment. An uncertain delivery needs reconciliation, not a new post.

Verified here: capability response reports native events in a durable queue,
standard speed, existing ChatGPT login and initialized model-free Linear relay;
the installed tool schemas expose the calls above. No new job was started to
test this procedure. Local shell access alone is not a documented standalone
bridge dispatch command in this repo. Do not guess HTTP endpoints, launchers,
config paths or restart commands.

### Bridge version and recovery state

Coordinator-supplied state, 2026-10-31: private repository
`JB-barrel-droid/agent-bridge` exists with main and tag `v3.0.0-baseline`.
The completion digest is live from local branch
`codex/JEG-1422-completion-awareness` at `f3addf9`, not yet on the remote.
JEG-1447 settlement fix is built on `jeg-1447-settlement-fix` at `6c4eb318`,
not yet reviewed or live. Do not assume remote main reproduces the live digest,
or that a built settlement fix has shipped. Before recovery, reconcile the
running version, local patches, queue/checkpoints and reviewed remote state.

JEG-1440 owns reproducible restore documentation and the working pinned-tag
scratch-instance drill: runtime dependencies, launchd/config names (no values),
harmless event replay, provider/status checks and rollback without lost or
repeated queue items. Verify those receipts before claiming recovery works.
The installed connector is today's entry point; no standalone shell dispatch
command is specified here. No bridge-owned files or runtime settings change
in this ticket. If the bridge is down, continue cloud read checks, pause build
dispatch and mark in-flight jobs unknown. Never resubmit automatically.
Restarts and patch activation need Jeremy's named yes.

## Default successor and alternates (capability facts)

- PSpice (default): Jeremy's own direct Codex takes the whole coordinator role
  described above, subject to the pending review/merge decision. This Mac session has repo shell access plus Linear and Mac bridge
  tools. Access in another Codex environment must be checked there.
- ChatGPT Dots: per the charter, OpenAI's always-on agent on GPT-6 Astra,
  with its own cloud computer, browser and plugins; works with Codex in ChatGPT
  Space. No documented API; allowance undisclosed. It would coordinate through
  Linear, GitHub and its own connectors. This is the charter's description,
  not an independently tested integration or a claim of Mac access.
- Muse: charter-reported Linear read/comment access, GitHub as `jkb-bur-bot`,
  and no route to the Mac. Its pilot and permissions remain bounded by Jeremy's
  decisions; reporting capabilities does not authorize builds or merging.

## Open

- Jeremy must name who reviews high-risk work and who merges when Claude is
  unavailable, and approve a cutover clause. Existing standing merge text does
  not authorize a non-Claude merger. Keep affected PRs draft and blocked.
- Jeremy must set the Claude weekly-limit shift level and confirm the ledger
  is live; no numeric threshold is chosen here.
- Resolve neutral claim labels, queue exception and branch conventions against
  the Claude-only wording. This ticket's explicit Codex assignment is narrow,
  not a rewrite of `AGENTS.md` or permission for unrelated tickets.
- JEG-1445 uses `codex/JEG-xxxx-…` branches; any other provider's branch
  prefix or ownership label is Jeremy's call.
- Verify JEG-1440 restore/drill receipts and reconcile local live digest code
  with the remote baseline before any recovery or activation.
- After review, separately authorize/run JEG-1445 item 3: one small Todo pickup
  from Linear alone, recording each obstruction. No dry-run success claimed.

## Gap list

Line references are to current-main baseline `76ee1c41`; one line per dependency or distinct
instruction. Historical author names, `claude/` branch names and log paths alone
are not dependencies. `runbooks/` was searched in full for Claude/Duet and
provider-specific tools; its operational commands are provider-neutral, with
the inherited merge restriction noted below. No inventoried source is edited.

- `AGENTS.md:28`: historical all-Claude ownership text remains; read the usage-crunch review exception below it.
- `AGENTS.md:32`: outside a usage crunch independent reviewer must be Claude; crunch permits exact-head Codex light/standard only.
- `AGENTS.md:69`: merge batch executor must be a Claude merge session.
- `AGENTS.md:101`: ChatGPT/Codex model lane limited to explicitly authorized bridge builds.
- `AGENTS.md:112`: other-family drafts require the Claude lead to run the gate and merge.
- `AGENTS.md:143`: usage-crunch mapping still reserves high-risk review for Claude.
- `AGENTS.md:168`: integration, production QA, schedules and merge/deploy routed to Claude sessions.
- `AGENTS.md:173`: cheap-run restrictions retain the Claude merge dependency through rule 2.
- `AGENTS.md:179`: Muse PRs require Claude review.
- `AGENTS.md:222`: ticket label contract requires `claude` and uses `ready-for-claude`.
- `AGENTS.md:240`: ownership model assumes Claude cloud chat threads and Mac sessions.
- `AGENTS.md:243`: claimed owner label is `claude`.
- `AGENTS.md:250`: Backlog queue exception is `ready-for-claude`.
- `AGENTS.md:255`: claim procedure requires adding `claude` and removing `ready-for-claude`.
- `AGENTS.md:262`: heartbeat backup-branch convention assumes `claude/<ticket>-<slug>`.
- `AGENTS.md:296`: merge protocol executor is explicitly the Claude merge session.
- `AGENTS.md:353`: Mac-local `~/Projects/"fantasy tools"/Claude outputs/` is the only permitted access within that project folder; its player-news raw inputs are not recoverable from the repo alone.
- `AGENTS.md:400`: legacy claude.ai artifact and daily republish task remain pending live verification; independent access/control is not documented here.
- `CLAUDE.md:8`: user-level Linear/Usage Discipline instructions assumed available outside the repo.
- `CLAUDE.md:11`: delegation names Claude `deep-worker`/Opus and `worker`/Sonnet tools.
- `CLAUDE.md:13`: review subagents use Claude mappings except the explicit usage-crunch exception.
- `CLAUDE.md:19`: lead-thread rotation assumes Jeremy can start a replacement Claude thread.
- `CLAUDE.md:22`: direction-question tool is Claude's AskUserQuestion.
- `CLAUDE.md:24`: permission enforcement lives in Claude settings; another harness cannot assume it inherits those denials.
- `HANDOFF.md:9`: handoff maintenance assigned to the Claude lead.
- `HANDOFF.md:14`: Codex stopped; review and merge reserved to Claude.
- `HANDOFF.md:54`: JEG-1176 explicitly still requires independent Claude review.
- `HANDOFF.md:156`: before/after original is in Duet project files; ticket summary and later repo evidence must suffice or be reconciled.
- `HANDOFF.md:193`: #1105 delta reviews assigned to an independent Claude reviewer.
- `HANDOFF.md:394`: historical rollback copies point into cloud `/mnt/project-files/`; availability outside that environment is unverified.
- `HANDOFF.md:504`: another historical rollback-copy location needs availability checked before relying on it outside the cloud session.
- `HANDOFF.md:658`: active routine inventory lives in Jeremy's Claude Duet app.
- `HANDOFF.md:663`: routine stop action requires main Duet chat or Jeremy's app routines list.
- `HANDOFF.md:665`: handoff refresh depends on that routine and an unconfirmed main-chat change.
- `HANDOFF.md:672`: lane work is driven by the main-chat board task; steering/stopping requires Claude in Duet.
- `HANDOFF.md:677`: dedicated handoff writer is a Duet channel thread.
- `HANDOFF.md:735`: requirement sources include claude.ai memory and the Duet channel rather than solely durable records.
- `HANDOFF.md:768`: end-to-end ownership is Claude-only.
- `HANDOFF.md:778`: lane picks depend on Claude's pick and main Duet chat as source log.
- `HANDOFF.md:796`: open-question picks and authoritative log still assigned to Claude lanes/main Duet chat.
- `HANDOFF.md:841`: other model families require Claude T1 review and cannot merge.
- `HANDOFF.md:864`: ephemeral Claude cloud checkout cannot serve as durable recovery state.
- `HANDOFF.md:1086`: picks-log source remains in Duet; repo copy can lag.
- `runbooks/merging-prs.md:3`: inherits AGENTS merge protocol, whose executor is Claude-only despite provider-neutral check commands.
- `runbooks/heavy-suites-and-hot-files.md:3`: inherits the same restricted merge protocol; its heavy-suite checks themselves work without Claude.

Read observation: the initial older/dirty checkout lacked `HANDOFF.md`; the
fresh origin/main worktree contains it. Recover from current GitHub state,
not that older checkout. A mistaken read of `runbooks/heavy-suites.md` found no
file; the actual indexed file is `heavy-suites-and-hot-files.md`.

## Validation of this documentation change

`make validate` was attempted once on the Mac and failed in `sync` because
Playwright could not find `chromium_headless_shell-1208`. No browser was
installed and no retry was run. Generated app/dist changes are left unstaged
in the isolated worktree; only intentional documentation files are committed.
The gate must pass in CI before review/merge; no passing gate is claimed here.
Follow-up validation checks local Markdown links, refreshed source references
and whitespace; the missing browser is checked without installation or retry.
