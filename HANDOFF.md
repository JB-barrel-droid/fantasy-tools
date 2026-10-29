# Handoff: Data Driven Football (fantasy-tools)

Read this first if you are taking over this project (Codex, Claude, Muse or a
successor PM). `AGENTS.md` (every repo rule) and `CLAUDE.md` (Claude Code
specifics) still apply and win on conflict about repo process; this file adds
the live state, Jeremy's requirements and what only lived in chat. GitHub and
Linear hold the state, never a chat thread.

Maintained by the Claude lead session at Jeremy's request (2026-10-27 CT):
"Please maintain a takeover handoff in GitHub so Codex can continue this
project if your usage runs out." Update it before any large or risky change
and after each milestone; commit and push it with the relevant code.

---

## Resume here

### JEG-1249 corrections on #1105 (Claude, 2026-10-29 UTC)

- Same branch `claude/JEG-1188-two-level-bench`, PR #1105; includes #1108 (JEG-1241) at `dc10602d` by merge. Codex merges.
- ddf replacement is a player priced by identity in each source; market depth counts held players only; JEG-1241
  provenance wired into workspace.js / league.js, every reason fails closed; league-priced trades don't open in Compare.
- Jeremy, 2026-10-29: pastes are read as whole rosters (`coverage_unproven` doesn't block); a page that left its bench
  out still does. Error-checking design is a separate decision for him.
- Evidence: `docs/claude-log/pr-jeg-1188-two-level-bench.md` (JEG-1249 section). No Supabase change.

### Roster provenance helper (JEG-1241, Claude, 2026-10-29 UTC)

- Branch `claude/JEG-1241-roster-provenance`, draft PR only. New pure module `app/v2/roster-provenance-transitions.js`
  (`DDFRosterProvenance`) with a transition table fixture, node runner (22 source mutants) and Python wrapper. Not
  loaded by the page; not in any Makefile list yet.
- The #1105 owner (JEG-1188 session) agreed the API. Wiring in workspace.js / league.js is its follow-up PR after #1105
  and this PR merge. Contract: `docs/claude-log/2026-10-29-jeg-1241-roster-provenance.md`. Reasons `bench_omitted` and
  `coverage_unproven` are separate; which one gates is Codex's call (the owner proposes `bench_omitted` only, since no
  parser path attests a whole roster today).
- No merge, deploy or Supabase. Codex reviews and merges.

### League candidate completeness fix (Codex, 2026-10-28 UTC)

- Branch `fe/preserve-league-candidates`, separate from #1069. Fixes the
  per-opponent top-10 truncation before fit ranking and filtering; no value,
  fairness, or package-enumeration rule change. All qualified candidates remain.
- Synthetic default-size regression: 52 qualified trades, 22 sending JSN;
  old path retained 10 with zero JSN, corrected path retains all 52.
  Not a reproduction of Jeremy's current league or a promise about its JSN deals.
- Compact lazy fit details, cooperative fit evaluation/cancellation, and bounded
  cache retention prevent the naive uncapped full-fit memory regression.
  Optional size4 is still expensive; see the measured benchmark and limits in
  `docs/claude-log/2026-10-28-league-candidate-completeness.md`.
- Initial exact-head CI and isolated Mac browser tests passed. Release sequence
  gate opened after #1069 and #1071 published/live passed. Current main is being
  merged normally; fresh CI and independent delta review are required before merge.
  Parent coordinates Mac live QA. No Supabase changes.
  Linear issue creation was rejected by auto-review; do not retry without approval.

### JEG-1216 lineup presentation feature (Codex, 2026-10-28 UTC)

- Branch `fe/jeg-1216-lineup-stability` begins at PR #1062 candidate `50f76b95`. Keep it separate from active JEG-1213 release #1062 and do not merge to production until JEG-1213 lands.
- New shared `app/v2/lineup-comparison.js` exports `buildRows(before, after, shape)` and `renderTable(impact, shape, valueKey, caption)` as `TradeValueLineupComparison`. The former returns `{starters, bench}` groups of `{slot, before, after, changed}`; the latter returns a DOM wrapper containing the four-column table and a keyboard-accessible bench expander. Load order is finder, lineup-comparison, league, v2. Interactive Compare (JEG-1214) can call this helper directly.
- Draft [PR #1066](https://github.com/JB-barrel-droid/fantasy-tools/pull/1066) targets the release candidate, not main. League hookup, CSS, build registration and focused unit/browser tests are on this branch. The original JEG-1213 acceptance render flows also passed locally. See `docs/claude-log/2026-10-28-jeg-1216-lineup-stability.md` for commands and the intentionally stopped duplicate full gate. Final-head CI and independent review remain required before merge.

### Saved-team picker lane (JEG-1219, Codex, 2026-10-29 UTC)

- Draft [PR #1094](https://github.com/JB-barrel-droid/fantasy-tools/pull/1094), branch `codex/JEG-1219-saved-team-picker`. Both pair-finder sides select saved League teams as tab-local copies; untouched Your roster defaults only to the star, while explicit manual/session/link context wins. No finder roster/star writes or new UI/math scope. Source and required CI passed on `e1174207`; main `dbe06a7e` has since been merged normally and cleanly (merge `3e87c250`) under the parent's integration instruction, retaining #1071/#1072 runtime and data unchanged.
- Integrated runtime focused tests **15 PASS**; independent delta review and exact-head Preview/v2-render CI **PASS** on `35c18978`. #1086's working-copy mismatch was fixed at `8c677a23` and verified read-only; its module remains unloaded/unmerged here. Evidence: `docs/claude-log/2026-10-29-jeg-1219-main-integration.md` plus current PR/ticket metadata. Parent reports #1072 live gate passed; PR merge/deletion remains held.
- Follow-up fresh-page Bench backups fix (Linear comment `97fc817c`): backup buttons initialize the DOM `disabled` property instead of serializing `disabled=false`. Desktop/phone failing-before proof, focused **14 PASS/no skips**, independent delta review and exact-head CI **PASS** on `359d3613` (11 picker CI tests/no skips). No defaults, math, selectors or pending JEG-1237 folding changes; its #1100 patch still applies cleanly in a read-only check. Evidence: `docs/claude-log/2026-10-29-jeg-1219-backup-initialization.md` plus final PR metadata.
- Current release preparation: parent explicitly requested normal integration of main `a75b6a28`; clean merge `75e440ec` preserves all picker/backup code and brings in only data/history/monitoring. Current-data focused group **16 PASS/no skips**, independent delta review **PASS**; fresh final-head CI follows the documentation commit, without a full local-suite repeat. Parent then authorized #1094's first release slot after green exact-head gates and an immediately-before-merge healthy-main check; Jeremy approved this branch's automatic cleanup. Prior release hold is superseded only for #1094. Live Pages access here fails proxy HTTP 403, so provide published SHA/build to parent for the existing Mac QA task; no live browser success is claimed. Evidence: `docs/claude-log/2026-10-29-jeg-1219-release-preparation.md` and current PR/ticket metadata. No direct main push, force push, manual deletion, other PR release or Supabase change.

### League finder release batch (Codex, 2026-10-28 UTC)

- Authorized draft release only: `release/league-finder-20261028`, based on main
  `7e4f2603` (includes merged Pages speedup #1056 / `904d07ae`). Parent must
  finish #1056 publication/live QA before considering a production merge.
- Includes #1058/JEG-1213 `acd4b0c2`, with exact ancestral dependency heads
  #1043/JEG-1134 `d886fc9f` and #969/JEG-894 `391308ed`. Both are already in
  #1058, so merge #1058 once; no duplicate cherry-picks. Underlying PRs/tickets
  remain open. This release PR replaces serial dependency merges for this batch.
- Integration conflict only in this handoff: retained both lane sections.
  No application conflict or methodology change; current-main generated assets
  retained. Team-count support remains explicitly 8/10/12/14.
- Excludes #1059 release switch, source health, connector/Supabase and backlog.
  Focused combined suite: 27 PASS, no skips; workflow/shard parity: 68 PASS.
  Required final-head preview/v2-render CI pending;
  independent final review is parent-owned. No main merge or deployment authorized.
- Repair after independent review of `05859570`: finder and league links now
  carry complete value basis/player overrides, including explicit default replay
  over saved custom readers, for the visit only. Legacy links and position-share
  precedence remain unchanged. Focused release 13 and Overrides 3 PASS;
  new-head CI and one independent delta review pending;
  evidence: `docs/claude-log/2026-10-28-league-share-context-repair.md`.
- Delta review found league Undo left the imported value context active. The next
  repair snapshots and restores the prior visit-only context when an accepted
  league import is undone. Cancel leaves it unchanged. Evidence:
  `docs/claude-log/2026-10-28-league-import-undo-context.md`.
- Final independent review passed on `8e3bf8b8`. Current main `8cd3c26e`
  (fidelity pulse generated data only) was merged normally and cleanly afterward;
  the integration head needs fresh required CI. Main workflow green status was
  unavailable from this environment and must be verified before release merge.
  Evidence: `docs/claude-log/2026-10-28-league-main-integration.md`.
- Second current-main integration: `d9f617e0` (two generated health JSON files)
  merged cleanly; application/tests diff remains zero against independently
  reviewed code. Fresh release CI is required. Evidence:
  `docs/claude-log/2026-10-28-league-health-main-integration.md`.



### Pages validation lane (JEG-1170, completed 2026-10-28 UTC)

- #1056 merged as `904d07ae99320dc5d47ed3d38499af891d6c2dcf` and published at
  18:18:30 UTC. Parent reports Mac live QA passed; build
  `tv-20261028-1235-904d07a` matches the merge commit's -0500 timestamp
  (17:35 UTC). JEG-1170 is Done. This release prerequisite is complete.
- All exhaustive shards, artifact and rendered gates passed. Runtime was
  17m05s versus the 40m15s baseline. Queue time was a separate 25m36s;
  do not include queue time in the runtime comparison.
- Pages uses validate-base plus four exact-SHA core shards, all three rendered
  harnesses, and the successful build's artifact. Deploy requires success from
  every dependency. Existing cancellation and validation safeguards remain.
- Source: parent release verification update, 2026-10-28 UTC. This integration
  lane did not merge, deploy or independently repeat the Mac live check.

### JEG-1213 league-wide finder lane (Codex, 2026-10-28 UTC)

- Draft PR [#1058](https://github.com/JB-barrel-droid/fantasy-tools/pull/1058), branch `fe/jeg-1213-league-finder`. Implementation integrated; 23 targeted tests pass (20 ticket-specific unit/render + 3 existing UI regression methods). All internal subagents stopped; final head CI/review and parent merge/live checks pending. Read the live ticket and all comments (none at intake).
- Correction after CI repair: initial head contained #1043 `68b95fa5`. Later `d886fc9f` is now merged explicitly, as is main `2ccdcc79` (including merged #1044). Reuses #969 `391308ed`. Parent should land dependencies serially; this lane does not edit, merge or deploy those PRs. #1044 engine work remains separate.
- Scope: top-right transfer menu and league-settings sharing; paste cleanup, count warning and collapse; optional summary columns and filters for either team; #1 best opportunity, projections beside DDF, clear fit definitions and opponent totals/starters/construction, downgrade-package regression.
- Engine accepts only 8/10/12/14 teams: exact mismatch fix limited to those counts. Unsupported counts get an explanation; no engine methodology extension.
- Validation and exact head/PR recorded as milestones in `docs/claude-log/2026-10-28-jeg-1213-league-finder.md`. Parent owns merge/deploy/live checks; do not close JEG-1213 until live verified.


### Top summary (board lane, 2026-10-28 9:15 AM CT / 14:15 UTC)

Jeremy is near his usage limit, so Claude is stopping here. A successor picks up from this summary. The lane sections below are each lane's own notes.

- **Merge rule (Jeremy, Oct 28):** merge work he asked for on green CI plus a passed independent review, without asking him again. That includes PRs built on a logged pick, which he can reverse. Merge one PR at a time, wait for its Pages deploy and check the live site before the next. A pick alone never deploys a backend. Edge-function deploys (get-values, mcp) need his explicit yes. He keeps holds of his own (JEG-1125 / #1033).
- **Merged today:** #1023 (JEG-1190), #1027 (JEG-1176), #1028 (get-values week-flip fix), #1038 (JEG-1194), #1040 (render tests), #1031 (handoff), and #1030 (JEG-1187, Market supported, merged by the fit labels lane). #1023 and #1027 are confirmed live. The rest ride the Pages deploy for `059674f` (pending at 14:10Z); earlier deploys were cancelled by newer pushes. Deploys take 50 to 70 min, and a newer one cancels any that are pending. Confirm a Pages change by fetching its own file.
- **Edge functions (verified 13:45 UTC):** live `get-values` is v8 (13:00Z) and matches main, including #1028. Live `mcp` is v12 (04:27Z) and matches main as of #958. Both have verify_jwt false. Copies of both deployed versions for rollback are in `/mnt/project-files/ddf/edge-rollback-2026-10-28/`.
- **Reviewed and green, not yet merged (do next, one at a time):**
  1. #1029 (JEG-1189 bench check, tests only)
  2. #1034 (JEG-1155 week max 18)
  3. #1037 (JEG-1130 PMM copy part 2)
  Each passed independent review. Main was merged into each at 13:58Z, and their CI was re-running. Merge after green and check the live site after each. Then tell the Main green lane, which is holding #1035 until these deploys finish.
- **Approved by Jeremy, not yet done:** merge #1024 (JEG-1179 week default plus optional week; head `179288b`, reviewed PASS) and then #1032 (JEG-1123/1124; reviewed PASS; merge main in first, since both touch `mcp/tools.ts`, a clean auto-merge). Then deploy `get-values` (index.ts, league.ts, pipeline.ts) and `mcp` (index, rpc, tools, state, names, find-trades, viability, build, week) from main. Jeremy said "Yes, merge and deploy" (13:38Z). After the deploy, check that the live get-values returns players and that the connector answers with a "Week:" line. Roll back by redeploying the copies above if anything looks off. When #1032 merges, tell the connector size and names lane: its name-ambiguity fix builds on it and needs its own yes to ship.
- **Handed to other lanes:** #1022 (JEG-1180) goes to source freshness; review found a blocker, see the PR comment. #1030 went to fit labels (merged). Connector work after #1032 goes to connector size and names.
- **Picks log:** `/mnt/project-files/ddf/picks-log.md` (source of truth, every lane), copied into `docs/picks-log.md`. The Reversed column marks what Jeremy undid.

### Main green lane

Last updated: 2026-10-28 9:10 AM CT (14:10 UTC), by the Claude "Main green"
lane (paused: Jeremy's usage limit). Change: #1040 fixed the two render tests
#1023 broke; #1031 (handoff) merged; #1035 is green and reviewed, not merged.

- **Branch:** `main` (default branch, not protected, no rulesets). Every push to
  `main` triggers the "Deploy dashboard" workflow. Feature work happens on
  `be/<ticket>`, `fe/<ticket>`, `cma/<ticket>`, `muse/jeg-<id>-<slug>` and
  `banana/<...>` branches and lands by squash-merge PR.
- **Latest code commits on main (verified 13:40 UTC):** `4928cc2` (#1038,
  JEG-1194, board lane), `ed42c8e` (#1027, JEG-1176), `eec5157` (#1023,
  JEG-1190). Merged overnight by the Main green lane: #976, #1006, #1004, #1005,
  #963, #1011, #958, #920, #1021; #968 closed. #1028 merged by the board lane.
- **Deployed (verified 13:30 UTC):** the deploy for `abe781d` succeeded, so
  #1023 and #1027 are live. Deploys take 50 to 70 minutes and are atomic;
  confirm a change by fetching its own file, not by the build tag.
- **Render sweep on main: confirm (in flight at 14:10 UTC):** run 40700449750 on
  `31ccf10` (after #1040). Earlier run 40694747369 on `7bdd6e1` was red.
  #1023 makes Compare open empty with a Try a sample trade button, and the
  sample is now a real trade, so `test_v2_names_render` found no deal nets and
  `test_v2_plain_copy_render` lost the week line Compare hides once a trade is
  on (`#v2Compare.has-trade`). #1040 (merged as `b594b39`) fixes those two tests.
  Probe run 40696409208 (names fix only) passed shards 1 and 2; shard 3 failed
  only on plain_copy, which #1040 fixes. Make stops at the first failing module
  in a shard, and `make -k` does not change that.
- **Week 8 rebuild (JEG-1194, checked 14:10 UTC):** the site still serves
  week 7 for all seven sources (fixture built 2026-10-26 15:42Z). Chain run
  40689076971 (12:35Z, `ed42c8e`) built week 8 and passed `make validate`,
  but its push rebase conflicted on `dist/modules/source-import-health.json`,
  so its output was dropped. Run 40689841714 (queued 12:41Z) was still running.
  CBS week 8 was reloaded at 12:23Z (bake `cbswk8_2026-10-28t1223_v1`, 35 TE).
- **#1038 (merged `4928cc2`):** a red on a stored save newer than the live
  chart now holds only a build from that save (`judged_save`), never the live
  chart. `pipelines/chain_stuck_alert.py` opens one `chain-stuck` GitHub issue
  when the chain fails and the fixture is 6+ h old, and closes it on publish.
  Log: docs/claude-log/2026-10-28-board-publish-holds.md.
- **Next step (JEG-1194):** when run 40689841714 finishes, check that
  `data/history/index.json` on main serves week 8 and the live site says
  "data through Week 8". If it failed or conflicted again, read its log;
  dispatch a fresh chain only if none is queued. Open issues to file: a
  generated-file conflict drops a good rebuild; a parser fix never re-ingests
  (CBS reloads only when its page changes; the 12:07Z pg_cron job is gone).
- **Connector values (verified 13:45 UTC, board lane):** fixed. `get-values` was redeployed with #1028 at 13:00Z on Jeremy's yes, and the live trade tool returns players again. JEG-1157 is Done in Linear (In Review lane checked get_values, get_player_value and read_state live at 13:55Z).
- **What I am working on:** paused. Next step for a successor: read the result
  of render sweep run 40700449750 (fix any red module on a PR). Then, once the
  board lane's merges (#1029, #1034, #1037, #1036) have deployed, squash-merge
  #1035 (JEG-1193 phone chip; CI green on `110547c`, review passed; merge main
  into it first if it is behind), wait for its deploy, confirm the live
  `app/v2/v2.js` contains `noLink: PHONE_NAMES.matches`, and set JEG-1193 Done.
  #1043 (JEG-1134) also reworks the phone context row; if it merges first,
  merge main into #1035 and re-run its CI before merging.
  Jeremy's rule: work he asked for merges on green CI with a passed review,
  one at a time with a live check; backend and edge function deploys still need
  his yes. Other agents are actively merging to `main` every few minutes;
  see "Active agents and automation" below before touching any branch.
- **Next concrete action for a successor:**
  1. `git pull` on `main`, read section 7, then the Linear In Progress list
     (team Jegabee, project Trade Value Chart).
  2. Urgent: JEG-1177 (week transition A, per-source weeks), parent JEG-1176.
     Files: `pipelines/nfl_week.py`, `pipelines/check_rank_guard.py`,
     `.github/workflows/rebuild-chain.yml`, open PRs #1012 and #1022.
  3. Keep `main` green: the render sweep passes; JEG-982 (endpoint parity,
     edge function vs engine for 185 players) is still open.
- **JEG-1142 validation continuation (2026-10-28, Codex):** PR #1044, target branch
  `be/jeg-1142-promotion-off-v2`; local candidate `be/jeg-1142-validation-ready`.
  Includes author head `274f3126` and main `79b9b435`. Promotion/demotion stays
  off in all three engines; expected-start and bench math are unchanged.
  Contract CI failed because the probe clicked a player already in the sample;
  the author's helper fix is retained and reproduced green. Composite CI failed
  because its display-order guard disallowed exact-value ties with different
  tiers; the corrected guard retains every VP-7.3 check and rejects strict
  inversions. Independent reviews passed. Final make validate-base and both
  current reference comparisons pass; full core checks completed in resumed
  runs (see log for the initial environment error and corrected assertion).
  **Next:** check CI on the updated PR head; the parent alone coordinates merge
  and Pages verification. Do not close JEG-1142 before live switch and USO checks.
  No edge deploy or JEG-1205 work here. Generated output is retained uncommitted.
  Evidence: `docs/claude-log/2026-10-28-jeg-1142-conflict-resolution.md`.
- **JEG-1134 phone context row (Codex UI lane, 2026-10-28 15:37 UTC):** PR #1043, branch
  `fe/jeg-1134-context-phone-summary`, draft pending CI and parent review. Main `79b9b435` integrated by merge,
  preserving #970's single Copy link and both picks logs. New regression reproduced the clipped summary
  with overrides; on phones the indicator and Reset/Undo now use a separate strip immediately below the
  context row. All three states keep the row at 45px and its summary readable at 375/390px. Desktop keeps
  the indicator in its original row. The phone overflow menu is anchored to the row so Copy link fits on
  tabs without Customize. CI on reviewed head `68b95fa5` caught 2px summary clipping in DejaVu Sans at 375px;
  tighter phone spacing fixes it and the regression now runs both fonts. Ten targeted tests pass locally.
  See `docs/claude-log/2026-10-28-jeg-1134-fallback-font-ci.md` for this follow-up; new-head CI/review still required.
  The tap sweep reports exactly the same 23 error groups
  as clean main; its Reviewed-chip mutation leaves other hit-area rules intact. Full CI and live checks
  remain pending; see `docs/claude-log/2026-10-28-jeg-1134-context-review-fixes.md`. Parent coordinates release: no merge,
  deploy or deletion by this lane. #1035 remains a separate Reviewed-chip change; #967 stays superseded.
- **Incomplete changes / blockers:** #1035 above. Open decisions waiting on
  Jeremy are the `needs-review` tickets in section 7. Branch
  `scratch/oppanel-1129` could not be deleted (blocked as destructive); it is
  harmless, leave it. The same goes for `jeg-920`, `scratch/sweep-all`,
  `scratch/parity-1006`, `scratch/sweep-green-check` and `scratch/shard1-probe`
  (Main green lane scratch branches; deletes are blocked; no PRs).

- **JEG-1101 lane (Copy link explainer, updated 2026-10-28 9:35 AM CT):** PR #970
  merged as `26694ee` on all-green CI. Next: once the Deploy dashboard run for a
  commit at or after `26694ee` succeeds, confirm the live page shows Copy link
  with "Opens this view. A chat with the DDF tool reads it too." (fetch the page's
  own file, not the build tag), then move JEG-1101 to Done. The `mcp` tools.ts
  text change goes live only with an approved `mcp` deploy.

- **Fit labels lane (JEG-1187, JEG-1115; done 2026-10-28 10:15 AM CT):**
  Both shipped. JEG-1187: #1030 (`759a4f9`) makes Find a trade's Market
  supported fire on any gain the page shows (`theirNet > NET_FLOOR`); Deploy
  dashboard run 40703312106 (`0137a8a`, includes it) succeeded. JEG-1115: #1041
  merged (`1bd85f7`); Jeremy said yes and get-values v9 then mcp v13 were
  deployed from main (mcp v13 also carries #970's make_state text, JEG-1101).
  A live `find_trades` call returns `fit` and `fitReason` on every trade.
  Rollback copies of the previous live versions (get-values v8, mcp v12) are
  in the project files under ddf/edge-rollback-2026-10-28. Board lane: the live
  edge functions now include #1041, so later deploys from main keep it.
  Follow-up worth a ticket: a fitReason can list the other team's roster
  issues (e.g. "bench promoted to starter: Justin Jefferson" on a trade where
  Jefferson stays with them) without saying whose roster; same text as the
  page's `fitText`. #966 (Ba-Nana's earlier draft) is superseded by #1041;
  leave closing it to Jeremy.


### In Review tickets lane (2026-10-28, 9:10 AM CT)

- **JEG-1157** (live MCP no players): Done in Linear, live check above.
- **JEG-1156** (blank DDF Values after the week 8 flip): PR #987 was closed as
  superseded by #1010 (JEG-1177, merged), which is the per-source week default
  (more than half of DDF Value's sources on week N+1 picks N+1, else N; see
  `resolveWeekView` in curve-widget.js). The week selector itself is JEG-1178.
  Still In Review: it needs a live look at Player values showing filled DDF
  Values. Probe branch `probe/jeg-1156-live` (never merge) runs
  `tools/probe/jeg1156_live.mjs` in Actions run 40702410871 and prints
  `JEG1156-LIVE` lines (rows with a DDF Value vs total). Next step: read that
  log; if DDF Values are filled, comment the numbers on JEG-1156 and move it to
  Done (the selector stays on JEG-1178).
- Handed to their own lanes: JEG-894 (#969, main merged in at `b6cea06`),
  JEG-1101 (#970, main merged in at `2b1fe3e`), both still drafts; JEG-1142
  (branch `be/jeg-1142-promotion-off-v2` at `82cf1a7`, #999 re-applied, no PR
  yet, movers table still to do; get-values loads the site's value-model.js,
  so no edge deploy); JEG-1134 (draft PR #1043).

- **JEG-894 lane (share links, updated 2026-10-28 9:15 AM CT):** PR #969,
  branch `fe/JEG-894-share-links`, head `391308e` (main `31ccf10` merged in),
  marked ready for review, not merged. Jeremy approved the build (Oct 23),
  decision A with no privacy line (Oct 27), and said "Yes" to marking #969 ready
  and merging it once its checks pass (Duet, 2026-10-28 9:02 AM CT). The T1
  review on the PR and a re-read of the merged diff found no bugs. CI (preview
  run 40701218577, v2-render run 40701218597) was still running. Next: when
  both are green, merge main in again if it moved, squash-merge #969, wait for
  the Deploy dashboard run, open a Compare link and a Find a trade link in a
  fresh browser on the live site (JEG-894's acceptance criteria), then move
  JEG-894 to Done. If a check is red, look first at `test_v2_share_links_render`
  and `test_v2_contract_render` (reads `#v2CVerdictBar`, now inside
  `#v2CVerdictBarWrap`).

---

### Lane: Keep every source fresh (JEG-1200, JEG-1180, JEG-1201), 2026-10-28 9:10 AM CT

Stopped at 97% usage. State, verified 14:10 UTC:
- PR #1022 (JEG-1180, stale flag after Thursday 12:00 CT, runbook): review
  blocker fixed (`freshness_ok` follows `weeks_behind <= 1`, so a one-week
  stale source is a warning, not "Not updating"). Head 487ddaa. v2-render green;
  preview build was queued. Next: when the preview bot says validate passed,
  mark ready and squash-merge as "(JEG-1180)", wait for Deploy dashboard, check
  `dist/modules/reference-freshness.json` live.
- PR #1042 (JEG-1200, per-source "late" rules + hourly `source-lateness.yml`
  keeping one `source-late` issue): second review PASS at 6c5f589 (live week
  label due Wed 12:00 CT; offseason guard; exit 1 when the check can't run).
  Merge after #1022 (its doc links the runbook #1022 adds), then check the
  first scheduled run on main and the issue it opens.
- Live replay 13:57 UTC: only FantasySharks late (403 on every probe since at
  least Oct 22, never saved). At Wed 12:00 CT all seven site sources go late if
  week 8 still hasn't published (the site's history index is still week 7,
  fixture_built_at Oct 26 15:42Z; the board lane owns publishing). The probe log
  has no rows Oct 20-21.
- JEG-1201, three draft PRs with notes only (no code yet): #1050 post-validate
  isolation (hold only the source a failing test names, validate once more,
  fail closed; a post-validate hold on espn would never be released, needs a
  release step); #1051 hold-tolerance guard (run live-page/rank/week-history
  checks with each source held; suspected latent bug in
  `test_superflex.page_problems`); #1052 fill-in peers.
- Jeremy's decision (Oct 28, 9:03 AM CT): charts fill in missing players from
  FantasyCalc and the projection sources (espn, cbsros, razzball), never from
  another weekly chart ("Use fantasycalc and projections sources, those should
  be refreshing at least daily, so they are good"). FantasyCalc's own peers are
  the projections. Impact list: only moves over 5% AND over 2 trade-value points
  ("If the 5% only amounts to 1-2 trade value points, it's immaterial").
  chart_sigma and DDF weights also cross charts: report, don't change, without
  his yes.
- Linear: JEG-1180 and JEG-1200 In Progress (mark Done when merged and live);
  JEG-1201 In Progress. Due Nov 3-4: a Tue/Wed health comment on JEG-1176 for
  the week 8 to 9 flip.
- Exact next step: merge #1022 on green, then #1042, each checked live; then
  build #1052 (value math, Jeremy approved) with the impact list in
  /mnt/project-files/ddf/ or the PR body.

## Active agents and automation (keep current)

Checked 2026-10-28 03:30 UTC. Update this section whenever a lane, routine or
schedule starts, stops or changes. Before you work on a branch or ticket listed
here, coordinate first (bottom of this section).

**Claude (Jeremy's Claude Duet app):**
- **"DDF overnight keep-moving" routine**, from Jeremy's main Duet chat. Runs
  11 PM, 1 AM, 3 AM, 5 AM and 7 AM Central. Nudges the DDF lane threads and may
  ask the board thread to open PRs. Never merges, deploys, deletes branches or
  touches Supabase data. Stops itself after 2026-11-11 or when no DDF task is
  open. Stop it: ask Claude in Jeremy's main Duet chat to pause it, or pause it
  in the app's routines list (Jeremy only).
  Handoff upkeep (Jeremy, 2026-10-27 10:26 PM CT): on any run that changes the
  project's state, priorities, blockers or active agents, it refreshes
  `HANDOFF.md` and `docs/picks-log.md`, commits and pushes them with the
  relevant work, skips the update when nothing changed, and marks agent
  activity as verified or guessed. (Routine change made from the main chat;
  not yet confirmed from this thread.)
- **DDF lane threads** under the main-chat task "Run the Data Driven Football
  board": Clearing players and teams (JEG-1190, PR #1023), Main green (done
  2026-10-28 06:15 UTC, verified: queue merged, sweep green), Trade viability fix (JEG-1129, PR #960 merged), Board run / week
  transition (JEG-1176/1180, PR #1022). They open PRs, merge only what Jeremy
  approved (section 1) and log picks in `docs/picks-log.md`'s source. Stop or
  steer: tell Claude in Jeremy's main Duet chat.
- **This handoff thread** (Duet "ddf" channel). Writes only `HANDOFF.md`,
  `docs/picks-log.md` and claude-log entries.
- Not active: "Refresh DDF Value Logic page" (daily, disabled Oct 25) and
  "Hourly board check" (disabled Oct 2).

**Other agents (from `AGENTS.md`; activity inferred from open PRs, not checked
on their machines):**
- **Claude Managed Agent** (`session:cma`, `managed-agents/`): deployment
  `ddf-queue` runs hourly (America/Chicago), claims up to 3 Linear tickets
  labeled `session:cma`, and merges on green gates; `ddf-weekly-usage` runs
  Mondays 7 AM CT. Branches `cma/<ticket>` (open: #1003, #1011). Pause:
  `ant beta:deployments pause --deployment-id <id>` (ids in
  `managed-agents/README.md`; needs Jeremy's Anthropic account). It has a
  standing takeover of any ticket with no activity for 4 hours, so keep your
  heartbeat comments current.
- **Muse** (GitHub user `jkb-bur-bot`): only Linear tickets labeled `muse`;
  branches `muse/jeg-<id>-<slug>` (open: #981, #982, #1024). Never merges.
  Stop: remove the `muse` label or ask Jeremy.
- **Ba-Nana** (Grok Bot PM, `banana/*` branches; open: #963, #966, #967, #968).
  Its last handoff update was 2026-10-27 8:08 AM CT; whether it still runs is
  unknown. Runs live on grok-bot-vm (`/workspace/logs/`) and the Mac; stop by
  asking Jeremy.
- **Front-end sessions** `session:fe-pc` (Windows PC), `session:fe-mac`,
  `session:fe-cloud`, and `session:be`: owners are the Linear `Session` label.
- **Cursor cloud agent**: branch `cursor/mcp-assistant-outputs-b7b6` (PR #958).
- Other open PR branches: `research/position-weights` (#837), `fe/JEG-950`
  (#920), `fe/jeg-1107` (#939), `fe/JEG-890-team-summary` (#964),
  `fe/JEG-894-share-links` (#969), `fe/JEG-1101-llm-copy-help` (#970),
  `fe/jeg-1176-week-selector` (#1012), `exp/lagging-dist-probe` (#1025,
  experiment, do not merge). A `scratch/shard1-probe` render sweep was queued.

**Scheduled automation (no agent behind it):**
- Supabase pg_cron (project `iskiybsimubiujwuchsl`, times UTC), all active:
  `vintage-check-live` hourly (dispatches the rebuild chain when data changed),
  `source-probe-*` (fantasycalc hourly; projections, sharks, trade charts),
  `fidelity-pulse-live` every 3 h, `health-artifacts-live` every 6 h,
  `pages-deploy-live` 11:30, `rebuild-chain-bake-live` 11:45,
  `espn-weekly-store-*`, `player-status-history-*`, `projection-capture-sunday`,
  `player-identity-reconcile-nightly`, `render-sweep-daily`,
  `sleeper-identity-refresh-live`, `trigger-fantasycalc-weekly-save`,
  `trigger-player-trace-live`, `live-page-synthetic-live`,
  `cron-retention-30d`. List: `select jobname, schedule, active from cron.job`.
  Pausing one is a production change: ask Jeremy first.
- GitHub Actions schedule: `full-suite.yml` nightly 07:17 UTC. Everything else
  is push, PR or dispatch triggered.

**How to coordinate (for Codex or any successor):**
1. Check open PRs (`gh pr list`) and the branches above before touching the
   same files; two In Progress tickets may not share a hot file.
2. Announce a takeover with a comment on the Linear ticket
   (`taking over from <session> · last heartbeat <time> · continuing from
   <branch>`) and swap its `Session` label (`AGENTS.md`).
3. Ask Jeremy to pause the overnight routine before working the same branches
   as the Claude lanes (#1021, #1022, #1023).
4. Never force-push or rebase someone else's branch; merge `origin/main` in.

---

## 1. Jeremy's requirements, preferences, decisions, definition of done

Sources: Jeremy's own words in chat (claude.ai memory and the Duet "ddf"
channel, Oct 2026), `AGENTS.md`, `docs/decisions.md`, Linear tickets, and the
prior PM handoff on branch `banana/agent-handoff` (folded in below; that branch
is now history, last commit `d967e93`, 2026-10-27 8:06 AM CT).

### Product
- Data Driven Football (DDF) is a public fantasy football trade value site that
  compares trade-chart sources on one shared indexed scale. Pre-launch, no
  users yet (Jeremy 2026-10-07). Plan of record: Linear JEG-440 (GO LIVE, Done).
- **DDF Value** = the average of the weight-adjusted indexed values (not the
  trade chart average). **DDF Projections** = the average of the imputed values
  across projected sources. (Jeremy, 2026-10-27, verbatim definitions.)
- One headline DDF Value (trade-chart based); projections are shown with real
  numbers, never reduced to yes/no (JEG-1073).
- Bench value = league-wide bench VORP with a backup discount (JEG-1121).
- Check a Trade: neutral verdict naming the Charted vs Projected gap, plus one
  limitation line per value (JEG-1138).
- Paste-only league load at launch; the Sleeper/ESPN ID loader goes (JEG-1131).
- Copy direction is the PMM doc (lands in JEG-1130). Value copy says "based on /
  starting from" a source, never "copied from".
- Design language in PR #961 approved. Open: Fraunces headline font, warm paper
  vs mint background.
- JEG-1190 Compare a trade starts empty with a "Try an example" button (his pick
  A, 2026-10-27). JEG-1191 (rotating surprising example trades, new name) is
  backlogged.
- How he trades with it: seek the best DDF value arbitrage on his side while
  other managers react to market value, within each team's strengths and
  weaknesses; show trade options as a table.
- No risk-penalty logic until the JEG-1144 research lands.
- The trade viability rule is Jeremy's call (viability fix: PR #960, merged
  2026-10-28 02:43 UTC; next is a before-and-after on a real league for him).

### How he wants to work
- Claude owns DDF end to end; Muse is turned off for football work except
  tickets labeled `muse` (Jeremy 2026-10-26) or as a last resort he asks for.
- Supabase first for schedules, checks and orchestration (pg_cron, Edge
  Functions, `monitoring` schema); GitHub Actions for build, deploy and tests.
- He decides output logic and presentation, and prefers to edit after things
  are built. He defers engineering choices. Flag only one-way doors to him.
- Decisions go to him as multiple choice with context and a recommendation,
  one at a time with lettered options (2026-10-27: "present one at a time with
  multiple choice"; "show your recommendation when you present options").
- 2026-10-27: "Yes, use your picks, and make a note of what was picked in case
  I want to reverse something later." Lanes go with Claude's pick and log it in
  the picks log (source in Jeremy's main Duet chat; repo copy
  `docs/picks-log.md`). Nothing merges or deploys on a pick alone.
- 2026-10-27: approved merging DDF fixes to `main` on green CI with a passed
  review, one at a time, checking the live site after each. Bulk PR backlog is
  review-only; each backlog PR goes to him.
- 2026-10-27 backlog decisions: merge #1006, #1004, #1005, #963, #1011 (then
  close #968), #958 (then deploy mcp, approved); #920 new wording approved;
  close #997, #971; #837 stays open until its replacement lands. Sunday
  projection job and monitoring row approved. PR #960 viability fix: two
  backend function deploys approved.
- He asked for work to continue overnight, in parallel, on an ongoing basis.
- Every question to him carries a link, plain context and a recommendation;
  batch questions; never re-ask one he answered. After a live deploy, tell him
  what to check with a direct link to the page or tab.
- Never send PII or keys to model providers.

### Picks made for Jeremy (reversible)
Since 2026-10-27 9:45 PM CT the Claude lanes go with their own pick on open
questions and log it. Full list: `docs/picks-log.md` (copy taken 2026-10-28
03:22 UTC; source of truth is the log in Jeremy's main Duet chat until lanes
write to the repo). Nothing merges on a pick alone; every pick is reversible.
Current picks in brief:
- JEG-1190: Compare starts empty with a sample button worded "Try a sample
  trade" (PR #1023); clearing Your roster on Waivers clears it everywhere with
  a message and Undo; Clear league on Find a trade asks to confirm, with Undo.
- PR #1021: invisible 44x44 hit area for small phone footer links; re-freeze the
  basis test baseline from current main.
- JEG-1129: keep the backup WR rule at 1 (no code change).
- JEG-1180 (PR #1022): stale = any served week N after Thursday 12:00 CT of N+1;
  per-source freshness report is warning-only; DISCOVERY_OVERDUE alarm and the
  Central watchdog calendar unchanged; new health state names (current,
  lagging, stale, unknown).
- JEG-1180 (PR #1022, review fix): judged_at dropped from the freshness summary;
  New York date kept in check_weekly_freshness.
- JEG-1200 (PR #1042): live sources late after 9 h unconfirmed or when the site
  still shows last week after Wed 12:00 CT; weekly charts late when the week's
  article isn't out by Wed 12:00 CT; own GitHub schedule (watches pg_cron).

### Definition of done
- Done = merged to `main` and live (Linear "Done"). For a fix: commit, merge,
  wait for Actions, check the live site when published output changed.
- Bug fixes ship with a test that fails without the fix. Do not adjust tests
  to go green unless the assertion was wrong or Jeremy changed the rule.
- Value changes: JS engine, Python reference and spec reference on one branch,
  `value_check compare` at 0, rank guard at 0 inversions, before/after table
  on live data, 12-combo sweep for chart changes.
- Every session that changes anything writes `docs/claude-log/YYYY-MM-DD-slug.md`
  (Verified vs Claimed, not confirmed).

### Standing safeguards (Jeremy, 2026-10-27, verbatim where kept)
- Retain Standard, Half PPR, and PPR support.
- Clearly distinguish published, previous-season, modeled, stale, and unavailable data. Do not present labeled 2026 data as published 2027 projections.
- Do not discard unfinished changes or overwrite user work to make the repository look clean. If pushing fails, explicitly report what remains local.
- Commit and push HANDOFF.md regularly alongside the relevant code, after meaningful milestones, and update it before a large or risky change.

The Windows Excel/VBA/PowerShell, XLSM/Excel COM, workbook and macro-security
safeguards in the same request belong to a different project, not this one
(Jeremy, 2026-10-27: "Another project").

### Other hard rules (from the prior PM handoff and AGENTS.md)
- No force-push, no history rewrite, never rebase; merge `origin/main` into
  branches (Jeremy 2026-10-26).
- Runs from other model families never merge; output is a draft PR for a Claude
  T1 review. Never MiniMax 2.5 (M3 or newer only). No value math on cheap models.
- Never deploy the `mcp` edge function except the approved deploys above.
- Don't touch dirty generated files in the Mac checkout `~/code/fantasy-tools`,
  or `~/Projects/"fantasy tools"` beyond its `Claude outputs/` folder.
- Production Supabase writes and schema changes need Jeremy's approval.
- No big product decisions without Jeremy.

---

## 2. Repository, paths, branches

- **Repo:** https://github.com/JB-barrel-droid/fantasy-tools (public). Site:
  https://jb-barrel-droid.github.io/fantasy-tools/ (v2 pages under `/v2/`;
  ops status `/modules/status.html`; value logic `/value-logic/`).
- **Active branch:** `main`.
- **Known checkouts (not all verified):**
  - Mac mini: `~/code/fantasy-tools`, worktrees `~/code/wt/` (prior PM notes).
  - Linux box (grok-bot-vm): `/workspace/code/fantasy-tools`, worktrees
    `/workspace/code/wt/<JEG-n>`, launchers and logs `/workspace/logs/`.
  - Jeremy's machine: `~/Projects/"fantasy tools"` holds `data/raw` (33 MB,
    gitignored), the only copy of the retired player-news pipeline inputs.
  - Windows PC (`session:fe-pc`): path unknown.
  - Claude cloud sessions clone to `/home/claude/fantasy-tools`; ephemeral.
- **Branches with live work:** the head branches of the open PRs in section 7.
  `banana/agent-handoff` holds the superseded PM handoff (folded in here).

---

## 3. Architecture, key files, data sources, business rules

Entry docs: `SYSTEM_MAP.md` (map), `docs/architecture-current.md` (every file
the site reads and the job that writes it), `docs/methodology.md` (how values
are computed, with a step-to-code table), `docs/decisions.md`,
`docs/risk-register.md`, `docs/README.md` (doc index), `runbooks/README.md`.

```text
source data -> reference compute -> dashboard build -> frontend/site
(Supabase, pullers) -> (pipelines/, data/fixtures/current/) -> (make sync -> dist/) -> GitHub Pages
```

- **Front end:** `app/v2/` (v2 pages: `v2.js` shell, `finder.js` Find a trade,
  `trade.js` Compare, `targets.js`, `league.js`, `waivers.js`, `overrides.js`,
  `roster-paste.js`, `ddf-state.js`), plus the engine in
  `app/trade-value-chart/assets/`.
- **Value math (hot files, one In Progress ticket at a time):**
  `app/trade-value-chart/assets/value-model.js` (`runValuePipeline`, `// VP-x`
  step comments), `curve-widget.js` (curves, diagnostics, overrides API),
  `pipelines/value_reference.py` (Python reference) and its spec reference,
  `config/roster.json`, `config/lineup_parameters.json`,
  `pipelines/bake_players.py`, `app/v2/v2.js`.
- **Checks:** `pipelines/check_rank_guard.py` (publisher order kept, zero
  inversions), `pipelines/value_check.py compare`, `pipelines/nfl_week.py`
  (content week, flips Tuesday).
- **Data:** finished artifacts in `data/fixtures/current/` (e.g. `players.json`,
  `comparison-sources-data.json`); vendored inputs in `data/inputs/`.
- **Sources:** trade charts FantasyCalc, USA Today, FantasyPros, CBS;
  projections ESPN (anchor), CBS ROS, Razzball; also DraftSharks,
  FantasySharks, Sleeper (identity), nflverse (history). Pullers and syncs are
  the `*-supabase-sync.yml` workflows, `producers/`, `ops/watchdog/`.
- **Supabase:** project "JB-barrel-droid's Project" (ref `iskiybsimubiujwuchsl`,
  us-west-2). Edge functions in `supabase/functions/`: `get-values`, `mcp`
  (remote MCP connector), `usatoday-fetch`. Migrations and pg_cron schedules
  in `supabase/migrations/` (e.g. `gha_schedules_pg_cron.sql`). Local MCP
  server in `mcp-server/` (TypeScript). See `docs/values-endpoint.md`.
- **Managed agent:** `managed-agents/` (`session:cma`, queue run every 2 hours).
- **Sibling trees, not the chart:** `weekly_vegas/`, `waiver_wire/`.
- **Business rules (summary; full text in methodology/decisions):** Indexed is
  one order-preserving factor per chart and league setting (JEG-482); missing
  values stay missing, never zero; a shorter or longer chart list is filled in
  from other charts to full rosters (OC-5, VP-2.4); Buy/Sell needs at least 2
  sources backing DDF Value (JEG-1186); the trade finder judges the other team
  on the Indexed market (JEG-1129); Standard, Half PPR, PPR at 8/10/12/14 teams
  plus superflex.

---

## 4. Setup, development, build, test, deploy

Runtimes: CI uses Python 3.12 and Node 20. Python 3.13 and Node 22 worked for
the unit tests run here. Render tests need `playwright==1.49.1` with Chromium.

```bash
git clone https://github.com/JB-barrel-droid/fantasy-tools.git && cd fantasy-tools
python3 -m pip install playwright==1.49.1 tzdata && python3 -m playwright install chromium
npm ci --prefix tests/rendered_gate          # node render harness
cp .env.example .env                         # fill values yourself; never commit
make sync          # build dist/ (single publish path; stamps the build tag)
make validate      # deploy gate: reference, sync, guard harness, test-core, value-check, integration
make test-core     # core math tests only
make test-unit     # full suite (preview CI, non-blocking)
make preview-local # build and serve dist/ on :8000 (what production publishes)
make values-explainer MARK_REVIEWED=1   # after value-math narrative updates
make diagnostics   # chart checks without a browser
python3 verify_live.py [expected_build_tag]
gh pr checks <n> --watch ; gh run watch <id> --exit-status
```

Windows: the Oct 9 Mac handoff (`docs/claude-log/2026-10-09-handoff-mac.md`)
implies `make` needed workarounds on Windows; the exact Windows commands are
**unverified**. The `session:fe-pc` front end runs on his Windows PC, so don't
break the Windows path when changing build or test commands.

Configuration variable names (never commit values): `SUPABASE_URL`,
`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
`GITHUB_TOKEN`, `GH_TOKEN`, `LINEAR_API_KEY`, `ANTHROPIC_API_KEY`,
`FIRECRAWL_API_KEY`, `ALERT_WEBHOOK_URL`, `ALERT_MENTION`, `OPENROUTER_API_KEY`,
`MINIMAX_API_KEY`, `OPENAI_API_KEY`, `RENDER_TESTS_REQUIRED`, `CHROMIUM_PATH`,
`DDF_API_URL`, `DDF_MCP_URL`, `DDF_SITE_ORIGIN`, `DDF_NOW`, `EXPECTED_WEEK`,
`TRADE_VALUE_PLAYERS_JSON`, `TRADE_VALUE_COMPARISON_SOURCES_JSON`. Actions
secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GITHUB_TOKEN`,
`LINEAR_API_KEY`, `ANTHROPIC_API_KEY`, `FIRECRAWL_API_KEY`, `ALERT_WEBHOOK_URL`.

Gotcha (seen 2026-10-28): running `tests.test_rank_guard` /
`tests.test_spec_reference_value_pipeline` locally rewrote tracked generated
files under `app/trade-value-chart/` and `dist/` and left untracked
`dist/connect/`, `dist/ddf-skill.zip`, `dist/get-values.openapi.yaml`. Don't
commit that churn; `git checkout -- app dist` restores your own test output
(never run it over someone else's uncommitted work).

---

## 5. Deployment (GitHub Pages) and the deployed revision

- `.github/workflows/pages.yml` ("Deploy dashboard") runs on every push to
  `main` and on dispatch; Supabase pg_cron `pages-deploy-live` dispatches a
  daily rebuild at 11:30 UTC. It runs `make validate` and publishes `dist/`.
  Newer runs cancel older ones, and bots commit to `main` often, so wait for
  the first **successful** run that contains your commit.
- Identify what is live: the page's `<meta name="trade-chart-build"
  content="tv-YYYYMMDD-HHMM-<sha7>">`; `python3 verify_live.py <tag>`;
  `gh run list --workflow "Deploy dashboard" --branch main`; or
  `/modules/status.html` (live vs main build tag).
- Edge functions (`get-values`, `mcp`) are **not** deployed by Pages. They are
  deployed separately with Supabase (JEG-1049 is open to deploy on merge or
  check drift against main; PR #1003). Treat a merged edge-function change as
  source-only until a deploy is confirmed. The `mcp` deploy needs approval.
- Data refreshes: `rebuild-chain.yml` (dispatched by the hourly
  `source-vintage-check.yml` when vintages differ) commits refreshed fixtures
  to `main`, which redeploys.

---

## 6. Tests and checks actually run, results, known bugs

Run 2026-10-28 03:00 UTC in a cloud clone of `main` at `7594f41`
(Python 3.13.17, Node 22): `tests.test_rank_guard` OK (13, 3 skipped),
`tests.test_doc_staleness` OK (4), `tests.test_comparison_source_integrity`
OK (1), `tests.test_spec_reference_value_pipeline` OK (26). Not run:
`make validate`, render tests, the 12-combo sweep.

Known bugs (repro steps and history on each ticket):
- JEG-1157 / JEG-1156: live MCP `get_player_value` or `get_values` returns no
  players (reproduced above); blended DDF Values blank after the week-8 flip.
  Jeremy picked A (fall back to the latest published week, labeled). Fix PR
  #987 was **closed without merging** (checked 2026-10-28); find its successor
  on the tickets before redoing it. In Review.
- JEG-982: edge-function values differ from the engine page for 185 players
  (endpoint parity red test). In Progress.
- JEG-1135: render sweep red on main (overrides basis render test, shards).
  PR #1021 draft.
- JEG-1142: promotion model demotion penalty applies to almost every starter.
  In Review (needs Jeremy).

---

## 7. Prioritized unfinished work

1. JEG-1177 Urgent (week transition A) under parent JEG-1176; JEG-1178 (B, site
   week selector, PR #1012); JEG-1180 (D, stale flag, PR #1022).
2. Main green: render sweep green (JEG-1135 done 2026-10-28). Still open:
   JEG-982, JEG-1049 / PR #1003, JEG-1193 (needs Jeremy).
3. Waiting on Jeremy (`needs-review`): JEG-1156, JEG-1157, JEG-1142, JEG-1134,
   JEG-955, JEG-956, JEG-903, JEG-1176, JEG-982. (JEG-894 and JEG-1101 are
   decided; PRs #969 and #970 merge on green.)
4. JEG-1190 clear players and teams on every screen (`session:fe-cloud`); its
   PR is not merged without Jeremy's call.
5. JEG-890 team value summary (PR #964), JEG-1093 Mac review notes, JEG-927
   mobile umbrella (PR #963).
6. Open PRs (2026-10-28 03:30 UTC): see "Active agents and automation" for
   owners. #1005 merged at 03:15 UTC. Apply the section 1 backlog decisions;
   don't merge others without review.
7. Connector answers and name matching (JEG-1123, JEG-1124; Claude lane
   "connector answers smaller, names smarter", checked 2026-10-28 14:10 UTC).
   JEG-1123 (top-5 text, data once in structuredContent, limit honored, size
   caps) and the 2-character name minimum are in PR #1032, which the board
   lane owns and merges after #1024 with the mcp deploy Jeremy approved. Typo
   matching, "Closest:" suggestions and Allen/Jr ambiguity are already on
   main (#958). One gap is built but not pushed as code: `compare_trade`
   still totals a trade without a name that fits several players. Patch:
   `docs/claude-log/2026-10-28-jeg-1124-ambiguity.patch` (stops compare_trade
   and asks which player; `find_trades` / `find_trades_league` count and list
   ambiguous roster names in text and structuredContent; new tests; sizes
   unchanged; all connector tests green on #1032 + main). **Next step:** once
   #1032 is on main, branch from main, `git apply` the patch, run
   `tests/node/mcp_remote_check.mjs`, `batch_trade_check.mjs` and
   `python3 -m unittest tests.test_mcp_remote`, open a PR, merge on green CI +
   review, log the two picks (compare stops and asks; roster scans keep going
   and list the name). Putting it live needs another mcp deploy: Jeremy's yes.
   Backlog: JEG-1202 (store ESPN, Sleeper and Yahoo spellings of every player
   name; production data writes need Jeremy's yes).

Failed approaches and traps:
- Two PRs on `curve-widget.js` merged minutes apart broke deploys twice: merge
  one engine PR at a time and re-run `make test-core`.
- Don't re-add a schedule to `fantasycalc-drift.yml` or restore its publish
  path; don't apply `supabase/migrations/jeg427_fantasycalc_weekly_save.sql`
  without re-checking (Oct 7 warning: a 12-team-only bake mislabels weeks).
- Retired: `sourceScaleAgreement`, per-position correction layer, cap at 70,
  the `*_adjusted` fixture sections, the lanes/outbox protocol, player-news.
- Parallel browser test runs saturated the Windows PC; run heavy suites on one
  machine, sequentially.
- MiniMax 2.5 output was poor; free OpenRouter models hit 429s.

---

## 8. Files and data outside git

- `data/raw/` (gitignored): raw pulls; the player-news inputs exist only on
  Jeremy's machine. Other raw data is re-pulled by the sync workflows.
- `output/` (gitignored): regenerated by the `make` targets.
- `dist/v2/`, `dist/classic/`, `dist/assets/history/`,
  `app/trade-value-chart/assets/history/`, math-inspector files (gitignored):
  regenerated by `make sync`.
- `.env`: copy `.env.example`; values come from Jeremy, the Supabase dashboard
  or GitHub Actions secrets. Edge function secrets live in Supabase.
- Outside the repo: Linear (team Jegabee, project Trade Value Chart) is the
  progress record; the feature contract and manifesto Google Docs
  (`docs/feature-contract.md`, `docs/manifesto-mirror.md` are mirrors); the
  source picks log in Jeremy's main Duet chat (copied to `docs/picks-log.md`); PM launchers and wrappers
  on the grok box (`/workspace/logs/`) and Mac (`~/.config/banana/`); the old
  DDF Value Logic artifact (retires once the dashboard page is verified live).
- Nothing of this session is unpushed or uncommitted.

---

## Keeping this file current

- Rewrite "Resume here" in place and bump "Last updated"; don't append logs.
  History lives in git, Linear, PRs and `docs/claude-log/`.
- Update it before a large or risky change and after each milestone, in the
  same push as the code when possible.
- Delete what is resolved; link to Linear and GitHub instead of copying them.
- Keep "Resume here" under about 40 lines.
