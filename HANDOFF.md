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

Last updated: 2026-10-27 10:35 PM CT (2026-10-28 03:35 UTC), by the Claude
lead session (claude.ai Duet "ddf" channel, handoff thread). Change: added the
picks log copy (`docs/picks-log.md`) and the "Active agents and automation"
section; the overnight routine now owns handoff upkeep.

- **Branch:** `main` (default branch, not protected, no rulesets). Every push to
  `main` triggers the "Deploy dashboard" workflow. Feature work happens on
  `be/<ticket>`, `fe/<ticket>`, `cma/<ticket>`, `muse/jeg-<id>-<slug>` and
  `banana/<...>` branches and lands by squash-merge PR.
- **Latest relevant code commit on main:** `03807db` "Bench spread by cut: role
  cut vs budget cut (part of JEG-859) (#1005)", 2026-10-28 03:15 UTC. Later
  commits on main are this handoff (docs) and bot status commits.
- **Deployed (live) revision:** the last successful "Deploy dashboard" run is
  for `fde5b9e` (#1020, JEG-1175 transition replay), checked 03:30 UTC; at
  03:00 UTC the live `trade-chart-build` meta tag read
  `tv-20261028-0141-abc4675`. Re-read the tag to confirm. **In source only**
  until a deploy succeeds: `2e90b88` (#960, JEG-1129 trade viability: judge the
  other team on the Indexed market), `561d576` (#1006), `7594f41` (#1004),
  `03807db` (#1005). Deploys keep getting cancelled by newer pushes.
- **Rebuild chain is failing (JEG-1194):** every run since 2026-10-26 15:42Z;
  the site stays on week 7. Latest cause: a red CBS fidelity hold (week 8 save,
  0 TE rows) grayed out the live week 7 CBS chart and test_superflex failed.
  Fix on `be/jeg-1194-board-publish` (hold scope + stuck-chain issue alert) and
  #1027 (lagging-chart tests). See docs/claude-log/2026-10-28-board-publish-holds.md.
- **What works (verified 2026-10-28 03:00 UTC):** the live site serves at
  https://jb-barrel-droid.github.io/fantasy-tools/ with the build tag above;
  quick unit tests pass locally (see section 6).
- **What is broken now (verified):** the live DDF MCP connector returns no
  players. `get_player_value` for "Josh Allen, Bijan Robinson" (half PPR, 12
  teams) returned `player: null` for both with `as_of 2026-10-26`. This is
  JEG-1157 / JEG-1156 (In Review, waiting on Jeremy). Not re-checked: whether the
  site's blended DDF Values are still blank (JEG-1156).
- **What I am working on:** this handoff only (docs). No code change of mine is
  in flight. Other agents are actively merging to `main` every few minutes;
  see "Active agents and automation" below before touching any branch.
- **Next concrete action for a successor:**
  1. `git pull` on `main`, read section 7, then the Linear In Progress list
     (team Jegabee, project Trade Value Chart).
  2. Urgent: JEG-1177 (week transition A, per-source weeks), parent JEG-1176.
     Files: `pipelines/nfl_week.py`, `pipelines/check_rank_guard.py`,
     `.github/workflows/rebuild-chain.yml`, open PRs #1012 and #1022.
  3. Keep `main` green: JEG-1135 / PR #1021 (render sweep), JEG-982 (endpoint
     parity, edge function vs engine for 185 players).
- **Incomplete changes / blockers:** none of mine. Open decisions waiting on
  Jeremy are the `needs-review` tickets in section 7. Branch
  `scratch/oppanel-1129` could not be deleted (blocked as destructive); it is
  harmless, leave it.

---

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
  board": Clearing players and teams (JEG-1190, PR #1023), Main green (PR
  #1021), Trade viability fix (JEG-1129, PR #960 merged), Board run / week
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
2. Main green: JEG-1135 / PR #1021, JEG-982, JEG-1049 / PR #1003.
3. Waiting on Jeremy (`needs-review`): JEG-1156, JEG-1157, JEG-1142, JEG-1134,
   JEG-955, JEG-956, JEG-903, JEG-894, JEG-1101, JEG-1176, JEG-982.
4. JEG-1190 clear players and teams on every screen (`session:fe-cloud`); its
   PR is not merged without Jeremy's call.
5. JEG-890 team value summary (PR #964), JEG-1093 Mac review notes, JEG-927
   mobile umbrella (PR #963).
6. Open PRs (2026-10-28 03:30 UTC): see "Active agents and automation" for
   owners. #1005 merged at 03:15 UTC. Apply the section 1 backlog decisions;
   don't merge others without review.

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
