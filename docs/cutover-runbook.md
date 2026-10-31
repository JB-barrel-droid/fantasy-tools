# Cutover readiness

Scope: JEG-1445 items 1 and 2 only; the ticket-pickup dry run waits for review.
This is a procedure and gap inventory, not permission to change the rules.
Baseline inspected: `origin/main` at `48c61207`, 2026-10-31 UTC.
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

## Resume coordination without Claude

1. Read `HANDOFF.md`, then `AGENTS.md` and `CLAUDE.md` from current main.
   `AGENTS.md` wins over stale handoff process notes. Inspect `git status`,
   recent commits, Linear comments and open PRs before editing. Use an isolated
   approved worktree; leave other owners' dirty files alone.
2. Confirm the work was started by Jeremy or an authorized coordinator's
   label/state action. A spec is never an approval. For this ticket the
   coordinator already posted the claim: do not post a second claim.
3. Read Todo tickets by Linear priority, then oldest first. Backlog is not
   the queue. The `ready-for-claude` Backlog exception and `claude` owner label
   need a neutral replacement decision (Open below); do not silently apply
   them to a new provider. Work only within an explicitly assigned non-Claude
   scope until that conflict is settled. Do not work a parent directly.
4. Check comments, commits, PR updates, `Touches` and hot-file ownership.
   No two active tickets share a hot file or code path. A takeover requires
   four hours with no comment/commit/PR update, owner OK, or Jeremy's direction.
   Record `taking over from <session> · last heartbeat <time> · continuing
   from <branch>`; the previous owner must not resume. The separate branch
   rule permits only a normal main merge after 30 minutes without a push or
   owner OK; it is not permission to edit another owner's work.
5. For an authorized new claim, set In Progress and record `taken by
   <session/provider> · <UTC time> · branch <name>` plus the instruction source.
   Keep assignee Jeremy. State the model tier in the brief; Session, Model
   tier and BE priority label groups are retired. Use the branch and ownership
   exception explicitly assigned for non-Claude work; unresolved label policy
   goes to Jeremy rather than impersonating a Claude session.
6. At least every four active hours, every push and when parking, preserve
   what is done, next action and backup branch on Linear. Push validated work
   with an explicit `branch:branch` refspec; never bare push, main push,
   force-push or rebase. Check the branch's upstream and `git config
   push.default` first; an inherited upstream previously sent work to main.
7. Run the smallest meaningful check, then the required `make validate` gate.
   Heavy suites run sequentially on one machine; coordinate before starting.
   Stage only intended files: builds generate app/dist changes. Keep Verified
   separate from Claimed in the per-session `docs/claude-log/` entry.
8. Open a draft PR with the ticket id and risk label. Preserve exact head,
   check results, limitations and next action. Keep it draft while waiting:
   at most eight PRs may be ready for review. Review and merge remain blocked
   on the Claude-only rule until Jeremy names the replacement protocol.
9. If stopping, leave state, branch, files, commands/results, blockers and next
   action on the ticket, then return In Progress work to Todo. For a Jeremy
   decision, use In Review and `needs-jeremy`, with options and a recommendation;
   quote his answer with date before resuming. Do not mark Done before merged
   and live. This runbook grants no merge, deploy, deletion or credential change.

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

### What JEG-1440 still has to supply

As read, JEG-1440 is Todo. It owns the private bridge repo, tagged
`v3.0.0-baseline`, secret scan, approved remote and per-patch versions; a restore
note listing runtime dependencies, launchd and config names without values;
and a working pinned-tag test-instance drill with harmless replay and rollback
without lost or duplicated jobs. That note must provide the reproducible
installation/entry point needed by a new Mac shell or connector client.
These are requirements, not claims that the tag, repo or drill exists today.
No bridge code or configuration is changed here.

Until recovery is verified, cloud read checks can continue when the Mac or
bridge is down; build dispatch pauses. Mark in-flight jobs unknown and never
resubmit automatically. Restarts and bridge activation need Jeremy's named yes.

## Candidate coordinators (facts, no ranking)

- Codex: this Mac session has repo shell access plus Linear and Mac bridge
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

- Jeremy must name who independently reviews and who merges when Claude is
  unavailable, and approve a cutover clause. Existing standing merge text does
  not authorize a non-Claude merger. Keep affected PRs draft and blocked.
- Jeremy must set the Claude weekly-limit shift level and confirm the ledger
  is live; no numeric threshold is chosen here.
- Resolve neutral claim labels, queue exception and branch conventions against
  the Claude-only wording. This ticket's explicit Codex assignment is narrow,
  not a rewrite of `AGENTS.md` or permission for unrelated tickets.
- JEG-1440 must publish and verify the reproducible bridge entry/restore path.
- After review, separately authorize/run JEG-1445 item 3: one small Todo pickup
  from Linear alone, recording each obstruction. No dry-run success claimed.

## Gap list

Line references are to baseline `48c61207`; one line per dependency or distinct
instruction. Historical author names, `claude/` branch names and log paths alone
are not dependencies. `runbooks/` was searched in full for Claude/Duet and
provider-specific tools; its operational commands are provider-neutral, with
the inherited merge restriction noted below. No inventoried source is edited.

- `AGENTS.md:28`: all review and merging assigned to Claude; Codex lane described as stopped.
- `AGENTS.md:32`: independent reviewer must be a Claude session other than the author.
- `AGENTS.md:57`: merge batch executor must be a Claude merge session.
- `AGENTS.md:89`: ChatGPT/Codex model lane declared inactive.
- `AGENTS.md:100`: other-family drafts require the Claude lead to run the gate and merge.
- `AGENTS.md:114`: integration, production QA, schedules and merge/deploy routed to Claude sessions.
- `AGENTS.md:120`: cheap-run output requires Claude review.
- `AGENTS.md:124`: Muse PRs require Claude review.
- `AGENTS.md:166`: ticket label contract requires `claude` and uses `ready-for-claude`.
- `AGENTS.md:184`: ownership model assumes Claude cloud chat threads and Mac sessions.
- `AGENTS.md:187`: claimed owner label is `claude`.
- `AGENTS.md:194`: Backlog queue exception is `ready-for-claude`.
- `AGENTS.md:199`: claim procedure requires adding `claude` and removing `ready-for-claude`.
- `AGENTS.md:206`: heartbeat backup-branch convention assumes `claude/<ticket>-<slug>`.
- `AGENTS.md:240`: merge protocol executor is explicitly the Claude merge session.
- `AGENTS.md:344`: legacy claude.ai artifact and daily republish task remain pending live verification; independent access/control is not documented here.
- `CLAUDE.md:8`: user-level Linear/Usage Discipline instructions assumed available outside the repo.
- `CLAUDE.md:11`: delegation names Claude `deep-worker`/Opus and `worker`/Sonnet tools.
- `CLAUDE.md:13`: lead-thread rotation assumes Jeremy can start a replacement Claude thread.
- `CLAUDE.md:16`: direction-question tool is Claude's AskUserQuestion.
- `CLAUDE.md:18`: permission enforcement lives in Claude settings; another harness cannot assume it inherits those denials.
- `HANDOFF.md:9`: handoff maintenance assigned to the Claude lead.
- `HANDOFF.md:14`: Codex stopped; review and merge reserved to Claude.
- `HANDOFF.md:29`: JEG-1176 explicitly still requires independent Claude review.
- `HANDOFF.md:131`: before/after original is in Duet project files; ticket summary and later repo evidence must suffice or be reconciled.
- `HANDOFF.md:168`: #1105 delta reviews assigned to an independent Claude reviewer.
- `HANDOFF.md:369`: historical rollback copies point into cloud `/mnt/project-files/`; availability outside that environment is unverified.
- `HANDOFF.md:479`: another historical rollback-copy location needs availability checked before relying on it outside the cloud session.
- `HANDOFF.md:633`: active routine inventory lives in Jeremy's Claude Duet app.
- `HANDOFF.md:638`: routine stop action requires main Duet chat or Jeremy's app routines list.
- `HANDOFF.md:640`: handoff refresh depends on that routine and an unconfirmed main-chat change.
- `HANDOFF.md:647`: lane work is driven by the main-chat board task; steering/stopping requires Claude in Duet.
- `HANDOFF.md:652`: dedicated handoff writer is a Duet channel thread.
- `HANDOFF.md:710`: requirement sources include claude.ai memory and the Duet channel rather than solely durable records.
- `HANDOFF.md:743`: end-to-end ownership is Claude-only.
- `HANDOFF.md:753`: lane picks depend on Claude's pick and main Duet chat as source log.
- `HANDOFF.md:771`: open-question picks and authoritative log still assigned to Claude lanes/main Duet chat.
- `HANDOFF.md:816`: other model families require Claude T1 review and cannot merge.
- `HANDOFF.md:839`: ephemeral Claude cloud checkout cannot serve as durable recovery state.
- `HANDOFF.md:1061`: picks-log source remains in Duet; repo copy can lag.
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
in the isolated worktree; this PR contains only the three requested docs.
The gate must pass in CI before review/merge; no passing gate is claimed here.
