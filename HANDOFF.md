# Data Driven Football — takeover handoff

Updated 2026-10-28. Read this and [AGENTS.md](AGENTS.md), then the current
Linear ticket and PR diff. Linear is the queue; GitHub is the code/review
record. Do not load every historical lane memo for a routine review.

## Resume here

- Repo: [fantasy-tools](https://github.com/JB-barrel-droid/fantasy-tools).
  [Live site](https://jb-barrel-droid.github.io/fantasy-tools/).
  [Takeover queue](https://linear.app/jegabee/document/takeover-queue-and-backlog-map-2026-10-28-9124ef66830c)
  gives ordering; each groomed ticket contains its current brief.
- First verify JEG-1177's week-8 publishing and the latest main render sweep
  (handoff run 40700449750). JEG-1206 tracks generated-file conflicts dropping
  otherwise valid rebuilds. Do not redo merged #1010/#1027.
- Reviewed board queue: #1029 (JEG-1189) → #1034 (JEG-1155) →
  #1037 (JEG-1130). Then #1035 (JEG-1193); coordinate its v2.js edits
  with #1043 (JEG-1134).
- Connector order: #1024 (JEG-1179) → #1032 (JEG-1123/1124).
  Jeremy explicitly approved these merges and corresponding get-values/mcp
  deploys on Oct 28 at 13:38Z. Reconcile current main before shipping.
- #1044 turns off all promotion/demotion math (JEG-1142, decided Oct 27).
  Keep starter/bench weighting. JEG-982's historical mismatch is diagnosed:
  stale test hold semantics and later test-clock drift; #898/#1006 fixed
  these. Rerun current parity before closing; do not assume a live value bug.
- #970 merged as 26694ee; verify Copy link wording live. Other PR briefs,
  current-head CI and the ticket supersede old retry/ownership memos.
- Freshness: #1022 → #1042. JEG-1204/#1051 tests held sources before
  JEG-1203/#1050 isolation; JEG-1205/#1052 implements approved fill peers.
  Those three drafts contain notes only. JEG-1207 tracks parser replay.
- Explicit holds: JEG-1125/#1033 is not released by green CI; JEG-557/#982
  waits until its outdated research is refreshed against stable logic.
- #967 and #966 are superseded by #1043 and #1041 respectively. Keep their
  history/branches; review the replacements.
- Week 8→9 acceptance: verify JEG-1176 health Nov 3–4 before closing.

## Shipping and deployment boundaries

Requested work merges on current green CI and passed independent review
under Jeremy's Oct 28 rule, one PR at a time, with a successful Pages deploy
and a live check before the next. Repo lead/reviewer restrictions in
AGENTS.md still apply. A logged pick is reversible and is not itself a
deployment approval. Jeremy permitted Claude lanes to use reversible picks
logged in docs/picks-log.md (Oct 27); preserve the scope of that authorization.
Do not ask again for an approval already recorded.

Edge functions are separate from Pages. #1024/#1032's approved deploy does
not cover #1041 or JEG-1124's residual ambiguity patch. Production Supabase
writes/schema changes and other edge deploys require Jeremy's explicit yes.

For the approved pair, the prior lane recorded:
- get-values: index.ts, league.ts, pipeline.ts.
- mcp: index, rpc, tools, state, names, find-trades, viability, build, week.
- Verify live get-values returns players and connector output includes Week:.
- Rollback copies were at /mnt/project-files/ddf/edge-rollback-2026-10-28/
  in the prior lane's environment. Confirm availability before deploying;
  that path is not guaranteed in a new checkout.

Last deployment observation (13:45 UTC, inherited, not rechecked here):
get-values v8 matched main through #1028; mcp v12 matched #958. Both used
verify_jwt=false. Never infer deployment from a merge or this old observation.
Fetch the changed served file, not only the build tag. Pages runs can be
cancelled by newer pushes; a successful containing commit is what matters.

## Pending decisions and model traps

- Jeremy chose no role-change/risk speculation for anyone (JEG-1142).
- Fill-in peers: FantasyCalc and projections for weekly charts; projections
  for FantasyCalc. Report moves only when both >5% and >2 value points.
  Do not change chart_sigma or DDF weights without a separate decision.
- Final copy decisions and limitations are on JEG-1130/1138/1102. Do not
  resurrect superseded names or single-winner proposals from old comments.
- JEG-1124's remaining patch:
  docs/claude-log/2026-10-28-jeg-1124-ambiguity.patch. Apply only after #1032;
  compare_trade stops on ambiguity, roster scans list/count it and continue.
  Run mcp_remote_check.mjs, batch_trade_check.mjs and tests.test_mcp_remote;
  new PR and fresh mcp-deploy approval are required.
- JEG-1061/#981 lacks the requested compute/rate-limit logging scope;
  resolve that gap before calling it complete.
- #837's tables are stale; continued work is on cma/JEG-925.
  tools/research_post9_numbers.py refuses incomplete-source snapshots.
- Do not restore fantasycalc-drift.yml scheduling/publishing or apply
  jeg427_fantasycalc_weekly_save.sql without checking the week/grain issue.
- Retired: sourceScaleAgreement, per-position correction, cap at 70,
  *_adjusted fixture sections, lanes/outbox dispatch and player-news.
- Retain Standard/Half PPR/PPR; distinguish modeled, stale, previous-season,
  unavailable and published data. Never turn missing values into zero.

## Coordination and automation

Check current PR heads, ticket activity and hot-file overlap before work.
Old session/owner/wave/BE labels were removed at Jeremy's request; do not
restore them or infer an active owner from an old label. Keep one current
status rather than a stream of takeover/CI-wait memos.

Agent activity is not freshly verified. The older lane record described:
- Duet “DDF overnight keep-moving”: 11 PM, 1/3/5/7 AM Central until Nov 11
  or no open work. Nudges only; no merges/deploys/deletes/data writes.
  Jeremy controls its pause from his main Duet chat.
- Claude Managed Agent was retired Oct 27, but schedules kept firing.
  JEG-1173 owns teardown of ddf-queue and ddf-weekly-usage; inspect actual
  account state before claiming stopped. IDs/config: managed-agents/README.md.
- “Refresh DDF Value Logic page” and “Hourly board check” were disabled;
  do not restart them. Retire the old artifact only after JEG-1107 is live.

Supabase project: iskiybsimubiujwuchsl (us-west-2). pg_cron owns source probes,
vintage/rebuild dispatch, fidelity, health, identity and scheduled captures;
GitHub Actions owns tests/build/Pages. Inspect current cron.job and
docs/watchdog.md for schedules; pausing production schedules needs approval.
Do not treat historical schedule lists as present health.

## Files, commands and evidence

- Architecture: SYSTEM_MAP.md, docs/architecture-current.md.
- Math/decisions: docs/methodology.md, docs/decisions.md, docs/risk-register.md.
- Source/test/deploy guides: docs/README.md and runbooks/README.md.
- Review only what is needed: [review-context.md](docs/review-context.md).
- Source → pipelines/reference → data/fixtures/current → make sync → dist/.
  app/v2 contains UI; app/trade-value-chart/assets contains the engine;
  supabase/functions contains get-values and mcp. weekly_vegas and waiver_wire
  are separate sibling tools, not chart internals.
- CI uses Python 3.12/Node 20; some MCP checks require Node 22 type stripping.
  Browser checks need the pinned Playwright/Chromium setup in repo workflows.
  Windows command availability is unverified; preserve its working path.
- make sync builds; make validate gates; make test-unit is informational;
  make values-explainer MARK_REVIEWED=1 follows changed value narratives.
  Review runbooks/merging-prs.md and runbooks/verify-live.md before shipment.
- data/raw and output are untracked. The only player-news input copy is on
  Jeremy's machine; never touch ~/Projects/"fantasy tools" beyond Claude outputs/.
  .env values come from configured credentials; never print or commit them.
- Tests can dirty generated app/dist files. Do not commit that churn or
  discard another session's changes. No rebase, force push or history rewrite.

Older lane detail remains in
[the pre-cleanup handoff](https://github.com/JB-barrel-droid/fantasy-tools/blob/032cee07104c27e2bc2553de5061e3e639df3c67/HANDOFF.md)
and git history, plus immutable docs/claude-log entries. Read on demand;
these are dated evidence, not a second active queue.

## Maintenance

Rewrite current state in place after milestones; link to ticket/PR evidence.
Keep Resume here under about 40 lines. Never append per-agent memos,
duplicate the backlog, or copy whole CI logs into this file.
