# Coordinator takeover runbook: PSpice and Muse

Scope: JEG-1445 items 1 and 2 only; the ticket-pickup dry run waits for review.
PSpice is Jeremy's own direct Codex and the default successor for the whole
Duet coordinator role. Muse is the second named successor (Jeremy, 12:39:
"Muse should also be able to take over"). ChatGPT Dots remains an alternate.
Jeremy asked:
"Ensure PSpice will be able to take over at any time" and "Take your role,
should it needed; is what I mean." This is a procedure and gap inventory,
with cutover review/merge ownership recorded under JEG-1444 decision 11 below.
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

## Shared cold-start checklist

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
  `get_completion_digest({consumer_id: "<stable successor consumer>", scope: "mac_jobs"})`.
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
  successor-readiness request first. Do not work a parent directly, duplicate a
  claim or share a hot file/code path with another active ticket.
- [ ] Claim only authorized work. Check comments/PRs first, set In Progress,
  preserve assignee Jeremy and use the assigned provider label (`claude` or
  `codex` for those providers; Muse label pending as described below).
  Record `taken by <exact session/provider> · <UTC time> · branch <name>` and
  instruction source. JEG-1445 uses `codex/JEG-xxxx-…`; another provider's
  branch prefix or ownership label remains Jeremy's call. Takeover follows
  AGENTS: four hours without comment/commit/PR update, owner OK or Jeremy's
  direction; log predecessor, last heartbeat and continuing branch.
- [ ] Dispatch cloud-first: use the acting successor's own tools when they suffice;
  send only the locally blocked portion to Mac jobs using the connector below.
  Require owner, linear_issue, starting commit, allowed/forbidden actions,
  check command, model/effort and reason. One provider per ticket. Retain the
  job id and operation key for uncertain starts. No auto retries; inspect the
  saved result before any separately authorized retry. Standard speed, fast off.
- [ ] Judge the result against the spec, changed files and named checks.
  Read CI on the actual PR head. A successful worker status is not a review.
  Review receipts must name the current head; after new commits request a
  delta review under the same risk floor, not another full review of old work.
  Muse findings start with `Written by Muse.`, include `<!-- author: muse -->`
  and use "recommend" wording;
  treat them as findings to verify, never approval or the independent PR review.
- [ ] Apply the merge gate and decision 11 below. Keep both documentation
  PRs draft as instructed; this task performs no merge.
- [ ] Track approvals by action, target, scope, date and source receipt on
  Linear. During cutover, decision 11 governs standard/light merges; Jeremy's
  specific yes remains required for high-risk merges, deploys, production-data
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

## Per-successor duty checklist

Both successors follow the shared checklist. Muse has no route to the Mac,
no push wake, posts Linear comments under Jeremy's name, and acts on GitHub
through the API as `jkb-bur-bot`. Do not infer Mac or connector access from
those identities. Where a required tool is missing, preserve the handoff and
report blocked; do not claim the duty ran.

### Queue reading

- **PSpice:** read Linear In Progress/Todo, charter JEG-1444 and children;
  inspect both repos' open PRs through its connector/CLI. Use its stable digest
  consumer, process/ack healthy pages, then save the event cursor.
- **Muse:** read the same Linear board and use GitHub API as `jkb-bur-bot`
  for PRs/heads/CI. Ask PSpice or an approved model-free bridge watcher for the
  digest/event summary because Muse cannot reach the Mac. Until that route
  exists, mark bridge state unknown; do not open results based on a stale copy.

### Triage and pick

- **PSpice:** finish the active ticket/corrections before picking one bounded
  Todo in charter order; check claims, blockers and hot-file ownership first.
- **Muse:** do the same through Linear; use visibly marked claims. If a label
  or state write is unavailable, hand it to PSpice or Jeremy and wait for the
  authorized claim rather than starting unclaimed work. Its provider ownership
  label remains pending; never claim to be `claude` or `codex`.

### Dispatch

- **PSpice:** use direct Codex cloud-first, and `mac_code_bridge` only for the
  locally blocked part, with owner, linear_issue and stable operation key.
- **Muse:** hand Mac dispatch to PSpice or an approved model-free watcher via
  a proposed Linear label, **`codex-mac` (pending approval and implementation)**.
  Do not create it or build a watcher here. Until that mechanism is approved
  and available, leave a marked request on the ticket for PSpice to pick up;
  no automatic dispatch is implied. Include task/checks, owner, issue, branch,
  operation key and approval scope, and obtain a job-id receipt. Track
  [JEG-1449](https://linear.app/jegabee/issue/JEG-1449), Muse's research into
  its own Mac route; research is not a working route or permission to use one.
  Transfer executor ownership explicitly before switching provider: one provider
  per ticket, no overlapping jobs. Neither successor retries or polls idly.

Pending executor lanes: OpenCode ([JEG-1423](https://linear.app/jegabee/issue/JEG-1423))
and Pi ([JEG-1438](https://linear.app/jegabee/issue/JEG-1438)) exist on local
branches only and are not live. Do not dispatch work to either lane yet.

### Judging

- **PSpice:** compare saved results, changed files, named tests and exact-head
  CI against the spec; request independent Codex review/delta receipts as below.
- **Muse:** inspect the same evidence using GitHub API and marked Linear
  findings; recommend acceptance or corrections. Request inaccessible Mac
  evidence through PSpice. A Muse finding is not the independent Codex review.

### Merge gate

[JEG-1444 decision 13](https://linear.app/jegabee/issue/JEG-1444), Jeremy
2026-10-31 13:16 UTC ("Add it to the charter"), applies to both successors.
Timing updated by Jeremy at 13:26 UTC: "One set of approvals at 6 am, one at
4 pm." No merge windows or approval asks overnight.

- **PSpice:** while Claude is out, run two batch and approval windows a day,
  at 6:00 AM and 4:00 PM US Central time (America/Chicago). Each gathers PRs
  that became eligible since the last window: at most 7 PRs of the same risk,
  each on its own reviewed head with green CI on that head. Group CI, review,
  branch integration, merge-gate wake-ups and deploy checks by release;
  never waive per-head evidence. Ask for the per-batch deploy yes naming the
  PR numbers in one multiple-choice question within that window, A recommended.
  High-risk and
  value-math changes ship alone; engine PRs stay one at a time. Urgent work
  (live numbers wrong or deploy broken) ships alone at once with normal gates.
- **Muse:** run the same 6:00 AM and 4:00 PM US Central batch and approval
  windows, gathering PRs eligible since the last one, obtaining the independent Codex
  receipt through PSpice if needed. Merge the batch only through GitHub API
  as `jkb-bur-bot`, with visible Muse attribution, `<!-- author: muse -->` and
  recommend wording in merge comments. Ask Jeremy for the per-batch deploy
  yes in that window in one multiple-choice question, A recommended, naming
  the PR numbers;
  a Muse comment is never his yes. If the API is unavailable, hand off without
  claiming a merge. Neither successor merges these PRs in this task.

For either successor, a PR conflicting after an earlier member merges waits
for the next batch: no mid-window rebase or repair. Afterwards its owner merges
`origin/main` normally, then obtains new-head CI and delta review. After the
batch, one CI run and one deploy check on main. If main goes red at any point,
stop the batch and diagnose; reverts use the normal gate. Deploys retain the
per-batch specific-yes requirement; the routine-data-refresh exception stays
unchanged. The two-window cadence and cap of 7 are defaults Jeremy can change.

### Approvals

- **PSpice:** keep an action/target/date/receipt ledger on the ticket and
  verify Jeremy's named yes for every specifically gated action.
- **Muse:** read the same receipts; its own Linear posts display Jeremy's
  name but never count as his approval. Hand settings operations to Jeremy's
  direct Codex and Mac operations to PSpice only within the named approval.

### Asking Jeremy

- **PSpice:** ask one real decision at a time, multiple choice, A recommended;
  read prior decisions first and do not repeat a settled question.
- **Muse:** use the same format with visible Muse attribution and "recommend"
  wording. If it cannot reach Jeremy directly, leave the marked question on
  Linear for PSpice to convey; do not treat its recommendation as an answer.

### Reporting and handoff

- **PSpice:** one milestone comment with a stable marker, exact heads, checks,
  limits and next action; check comments/relay state before posting or relaying.
- **Muse:** every Linear comment and GitHub post starts with the visible line
  `Written by Muse.`, includes `<!-- author: muse -->`, and uses "recommend"
  wording (for example, "I recommend the next step below"). Also include a
  distinct milestone marker for deduplication. A Muse comment is **never
  Jeremy's approval**, even though Linear shows it under his name. Check the
  marker first; no push wake or idle polling. Preserve any blocked handoff.

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
builds move to Codex. When Claude is out, decision 11 below supersedes the
normal Claude ownership mapping until it returns.
Before any authorized merge, require a current-head independent receipt,
green exact-head CI, clean merge onto current main, correction children closed,
no generated churn and the checks in `runbooks/merging-prs.md`. Never rebase or
force-push; merge main normally. Keep at most eight PRs ready for review.

### Cutover review and merge

Jeremy, 2026-10-31 12:42 UTC, answered "A" to who reviews and merges if
Claude is out: [JEG-1444 decision 11](https://linear.app/jegabee/issue/JEG-1444).
This section overrides normal Claude-only review/merge ownership only while
Claude is out. It is a documented operating policy, not permission to merge
these documentation PRs in this task.

- The one independent review comes from a separate Codex session that did
  not write the PR, on its exact current head. Use frontier `gpt-6-astra`
  for `review-high-risk` and workhorse `gpt-6.1-sol` for light/standard.
  Current-head receipts, delta reviews, risk floors and green-CI prerequisite
  still apply; the coordinator never substitutes its own check for review.
- The acting successor coordinator, PSpice or Muse, merges once that review
  passes and CI is green on that exact head, subject to the approval gates.
  The acting successor runs the same two daily batch and approval windows,
  at 6:00 AM and 4:00 PM US Central time, in the Review and merge protocol
  (JEG-1444 decision 13, timing updated 13:26 UTC), with no merge windows or
  approval asks overnight and with per-batch deploy approval naming
  PR numbers, isolated high-risk/value-math releases and immediate Urgent work.
  High-risk merges and all deploys still require Jeremy's specific yes.
  A yes covers only the named action and target; production-data deletion,
  credentials, Supabase migrations, GitHub settings, Mac patches and launchd
  activation retain their existing specific-yes requirements. Settings changes
  still go to Jeremy's direct Codex rather than the coordinator.
- Muse merges only through the GitHub API as `jkb-bur-bot`. Its merge comment
  starts with the visible line `Written by Muse.`, includes
  `<!-- author: muse -->`, and uses "recommend" wording. Its comment is never
  Jeremy's approval, even when Linear displays Jeremy as the author.
- When Claude returns, normal review routing in AGENTS.md applies again.
  Record the handback and pending heads/receipts so the same head is not
  reviewed twice. This temporary cutover rule does not activate a deployment,
  patch, routine or watcher.

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

## Named successors and alternate (capability facts)

- PSpice (default): Jeremy's own direct Codex takes the whole coordinator role
  described above, under decision 11 during cutover. This Mac session has repo shell access plus Linear and Mac bridge
  tools. Access in another Codex environment must be checked there.
- ChatGPT Dots: per the charter, OpenAI's always-on agent on GPT-6 Astra,
  with its own cloud computer, browser and plugins; works with Codex in ChatGPT
  Space. No documented API; allowance undisclosed. It would coordinate through
  Linear, GitHub and its own connectors. This is the charter's description,
  not an independently tested integration or a claim of Mac access.
- Muse (second successor): Linear read/comment under Jeremy's name, GitHub API
  as `jkb-bur-bot`, no push wake and no route to the Mac. Uses the duty handoffs
  above and decision 11; marking is mandatory. JEG-1449 researches Mac access.

## Open

- Jeremy must set the Claude weekly-limit shift level and confirm the ledger
  is live; no numeric threshold is chosen here.
- Resolve neutral claim labels, queue exception and branch conventions against
  the Claude-only wording. This ticket's explicit Codex assignment is narrow,
  not a rewrite of `AGENTS.md` or permission for unrelated tickets.
- JEG-1445 uses `codex/JEG-xxxx-…` branches; any other provider's branch
  prefix or ownership label is Jeremy's call.
- Verify JEG-1440 restore/drill receipts and reconcile local live digest code
  with the remote baseline before any recovery or activation.
- Approve/implement the proposed `codex-mac` label handoff or another researched
  route; neither a new label nor a watcher exists by virtue of this document.
- After review, run the two separately authorized cycles below. Neither has run.

## Dry-run plan (describe only; do not execute in this task)

1. **PSpice first:** from Linear/repo/GitHub alone, pick one authorized bounded
   Todo with a locally blocked step; claim, dispatch that one needed Mac job,
   consume/ack the digest then events, judge evidence and exact-head checks,
   and report one marked milestone with next action. Pass only if state is
   recoverable without Duet, the job-id/operation-key receipt and check evidence
   are saved, no duplicate start/comment occurs, and approval gates are observed.
   Record each obstruction and pause before any unauthorized merge/deploy.
2. **Muse second, after PSpice passes:** repeat pick, dispatch, judge, report.
   Exercise one approved Mac handoff and obtain its job-id/result receipt via
   PSpice or the approved watcher; until that route exists, record the cycle
   blocked rather than passing it. Pass only if Muse posts have visible/hidden
   attribution and recommend wording, GitHub evidence uses `jkb-bur-bot`, the
   handoff produces no provider overlap, evidence/markers are durable, and no
   Muse comment is mistaken for approval. Apply the same exact-head and
   specific-yes checks. A dry run never implies production rollout authority.

## Gap list

Line references are to current-main baseline `76ee1c41`; one line per dependency or distinct
instruction. Historical author names, `claude/` branch names and log paths alone
are not dependencies. `runbooks/` was searched in full for Claude/Duet and
provider-specific tools; its operational commands are provider-neutral, with
the inherited merge restriction noted below. This baseline inventory is historical: decision 11 and the matching rules PR
supersede the listed Claude-only dependencies during a cutover. Source line
references stay pinned to the stated main baseline, not to the rules PR.

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
