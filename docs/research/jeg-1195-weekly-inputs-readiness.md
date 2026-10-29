# JEG-1195 weekly inputs: evidence inventory and readiness

Research only (JEG-1195 prerequisite investigation, scoped by the 2026-10-29
ticket comment). Nothing in production changed: no runtime code, fetch,
Supabase write, math, default or design change. Supabase was read with
SELECT queries only. Repo state: `main` at `021c5bfd` (2026-10-29 UTC).

## Answer

- **The originals exist.** `weekly_vegas/README.md` and `waiver_wire/README.md`
  were moved, not lost: both products, their READMEs, runbooks, pipelines and
  last baked pages are on `main` under `archive/2026-10-07/`. Commit `fd370ab7`
  (PR #403, 2026-10-07) archived them as "products that do not connect to the
  v3 Trade Dashboard" and left retired-product stubs in the dashboard folders.
- **Neither can be re-run from the repo.** Both ran from a Hatch scheduler and
  `~/workspace/...` skills (Supabase client, PropLine, Odds API) that were never
  committed. The Vegas page builder and the waiver lottery scorer were never in
  git.
- **Versus Vegas is blocked** on two things only Jeremy can settle: there is no
  Vegas input on `main` (last odds row 2026-10-05), and the old comparison side
  was FantasyPros ECR, which left the project under JEG-ECR-EXIT.
- **The waiver dashboard is blocked** on missing inputs (no ESPN roster% puller,
  lottery scorer lost) and on JEG-556: its old waiver boundary is a second
  waiver-line definition and must be replaced by the repo's one rule.
- **What is ready now:** a shared weekly-input contract and producer built only
  from inputs that are current today (ESPN weekly projections, Sleeper status,
  byes, the content-week clock). Slices S1 and S2 below.

## 1. What was found in history

| Item | Location on `main` | Commit | Notes |
|---|---|---|---|
| Vegas product README | `archive/2026-10-07/weekly_vegas/README.md` | created `6d5f8701` (2026-09-22), archived `fd370ab7` | "Faithful copy of the operational source as of 2026-09-22" |
| Vegas daily runbook | `archive/2026-10-07/weekly_vegas/cron/daily-refresh.md` | same | Hatch job `weekly-signals-dashboard-refresh`, ~09:07 CT |
| Vegas methodology | `archive/2026-10-07/weekly_vegas/pipeline/docs/methodology.md` | same | |
| Vegas chain | `.../pipeline/bin/weekly_chain.py` → `engine/snapshot_v4.py` → `v4/compute_v4.py` | same | PropLine runs separately (`collectors/propline.py`) |
| Vegas baked page | `archive/2026-10-07/weekly_vegas/index.html` | `fd370ab7` (same blob as `31864bdd`) | Week 2, built 2026-09-21T14:29Z, 511 players |
| Vegas page builder | not in git | — | The bake injected `window.__WEEKLY_SIGNALS__/__WEEKLY_QA__/__WEEKLY_DELTA__`; no committed code writes them (`git log -S`) |
| Play-gate code | not in git | — | `compute_driving_prop` lived in workspace `lottery/bin/driving_prop.py`; thresholds survive in `engine/source_priority.py` |
| Waiver README | `archive/2026-10-07/waiver_wire/README.md` | same | |
| Waiver runbook | `archive/2026-10-07/waiver_wire/cron/weekly-refresh.md` | same | |
| Waiver builder | `.../waiver_wire/pipeline/bin/build_waiver_dashboard_data.py` `main()` l.891 | same | Uses `os` at l.359 and l.449 without importing it, so it cannot run as committed |
| Waiver lottery scorer | not in git | — | `score_v0.py` (cited by `waiver_delta.py`) filled the `lottery_*` tables |
| Waiver baked page | `archive/2026-10-07/waiver_wire/index.html` | `fd370ab7` | "Week 2 Waiver Board", as_of 2026-09-18, 12 teams |
| Tests | `archive/2026-10-07/tests/test_{game_day,weekly_chain}_espn_gate.py` | `95d6aa12`, `b7a0ddea` | Never in the Makefile; the waiver pipeline never had tests |

**Why and when retired.** `fd370ab7` (2026-10-07): "Archived products that do
not connect to the v3 Trade Dashboard". `.github/workflows/weekly-dashboard-load.yml`
l.8-15: manual only since 2026-10-08, "Weekly production is paused (JEG-ECR-EXIT
retired the ECR feed; JEG-399)... neither the trade-value chart nor the v2 site
reads the weekly dashboard tables".

**What the Vegas page showed (Week 2 bake).** Dataset health (8 freshness rows
plus a changed-since-last-build list), a 4-number scoreboard, Fantasy reads
cards (verdict, Vegas and ECR pair, reason, driving stat), All weekly players,
Snapshot provenance. Filters: scoring (std/half/ppr), position, search, coverage
(all/full/partial/missing/flagged), sort. Direction values `vegas_high`,
`experts_high`, `agree`, `no_market`. Labels: "Vegas (props-implied)", "ECR
(expert consensus)", "ESPN (Mike Clay model)". Provenance mix: td-filled 202,
partial 194, missing 81, complete 32, fds-derived 2; 11 post-worthy, 0 plays.

**What the waiver page showed (Week 2 bake).** Hot pickups 15, Other pickups 3,
Hold 10, Hold steady 49, Drop 6, Corrections 2, a 168-player browse list. No
don't-add section (`audit_waiver.py` l.12: "dont_add is gone"), no K/DST
streamers (`streamerData = null`), no week-over-week delta.

## 2. How the old builders worked (only what bears on a rebuild)

**Vegas.** Raw sportsbook props (PropLine primary; Odds API audit, code reserve
`QUOTA_RESERVE=60`; FDS fantasy-only fill, Sunday pre-kickoff) were translated
to fantasy points by `engine/vegas.py`. A leg no priced market moves is `None`,
never zero (`compute_v4.py` l.507-543). Provenance: `complete` and `td-filled`
publishable; `partial`, `fds-partial` informational; `fds-derived` publishable
but never a play (`engine/vegas.py` l.173-200, `engine/fds_fallback.py`
l.120-127). Play gate (`engine/source_priority.py`): edge ≥ 5 pp, line ≤ 24 h,
two-sided quote, Thursday ≥ 3.5 pts. Weekend builds failed closed without an
injury sync after Fri 18:00 CT (`compute_v4.py` `_require_injury_vintage`).
Known flaw: no-market rows null the Vegas fields but set `delta=0`
(`engine/no_market_read.py` l.101-126).

**Waiver.** One value-change re-ranking: old value = chart base + lottery edge,
new value = Monday legs (`impute_monday_tv.py`: `new_pg = prior + (form − prior)/9`,
`form = xFP + 0.10·FPOE`) × news multiplier + edge (`waiver_boundary.py`
`price_vector()` l.386). Rostered sets came from `starter_model.build_model`
with its own capacity and roster% gates (available below 70%, below 50% when
the new value is 10 or more; no roster% row = available). Priced from
`players.json` `blend_ppg` and `ecr_ppg` on a pinned 70 scale. The Vegas
signals file fed only a Week-2 source-comparison block, never sections or values.

**Identity.** Neither chain used the numeric key. Vegas rows keyed on a
lowercased name (`compute_v4.py` l.48; the page's `player_key` is `"rj harvey"`);
the waiver tree used `identity.py` `IdentityMap` (name strings).

**ECR.** JEG-ECR-EXIT (`6be39a20`, 2026-10-05): "Jeremy directive: full-season
ECR content exits the project". JEG-418 (`95d6aa12`) and JEG-419 (`b7a0ddea`)
switched only the freshness gates from ECR to ESPN ROS ("this ticket is the
gate only"). The core weekly build still read FantasyPros ECR CSVs
(`compute_v4.py` l.660-666, "a missing file raises"). JEG-421 (`d1e47cab`) built
`producers/build_staged_bundle_espn.py` with an ESPN expert leg, keeping ECR
field names.

## 3. Inputs today: current vs historical

Vintages read 2026-10-29 ~02:10 UTC. Content week 8 (`pipelines/nfl_week.py`).

| Input | Producer on `main` | Where | Vintage | Label |
|---|---|---|---|---|
| Canonical `player_key` | `pipelines/lib/canonical_players.py` (name rule, ambiguous → None); `pipelines/lib/player_key_index.py` `PlayerIndex` (Sleeper, gsis, ESPN id, then name) | `public.players.player_key` (bigint) | live | current |
| ESPN weekly projections | `pull_espn_projections.py` + `save_espn_weekly.py` (`espn-weekly-store.yml`, daily 12:40 UTC, Sunday 16:20 UTC `pre_kickoff`) | `public.projection_snapshots` (source espn); `data/inputs/espn_weekly_projections_2026.csv` | weeks 1-8, last 2026-10-28 12:40Z; 3 scorings (std/full derived ±0.5 per reception) | published |
| ESPN ROS | rebuild chain | `public.espn_season_projections`; `data/inputs/espn_projections.csv` | weeks 8-18, 2026-10-28 | published |
| CBS weekly | `pull_cbs_ros_projections.py` (current and next week) | `public.source_projection_captures` only | captured, no reader | modeled, not published |
| CBS ROS, Razzball ROS | probe and chain | `cbs_ros_projections`, `razzball_projections` | 2026-10-27/28 | published (ROS only) |
| Sleeper weekly projections | manual backfill | `data/inputs/weekly_projections_sleeper.csv.gz` | committed 2026-10-12 | stale |
| Player status, injury, depth | `save_player_status_history.py` (`player-status-history.yml`, daily 13:10 UTC + Sunday) | `public.player_status_history` | 2026-10-09 .. 2026-10-28 | current |
| Byes | static | `data/inputs/nfl_byes_2026.json` | season | current |
| Vegas props / odds | **none** (archive only) | `public.odds_history` | 2026-09-10 .. **2026-10-05** | stale |
| Vegas-implied points | **none** | `projection_snapshots` source `vegas_implied` | week 4 only, 2026-10-05 | stale |
| Weekly ECR | **none** (JEG-ECR-EXIT) | `projection_snapshots` source fantasypros | week 4 only, 2026-10-05 | unavailable by policy |
| ESPN injuries (legacy) | none | `public.injuries` | 2026-09-23 .. 2026-10-05 | stale |
| ESPN roster% | **none** (archived `engine/espn_roster.py`) | — | — | unavailable |
| Sleeper trending adds | none | — | — | unavailable |
| Usage trends | none | `public.waiver_trends` | 2024, 2025 full; 2026 week 1 only | previous-season |
| Lottery valuations | none (scorer not in git) | `public.lottery_valuations` | 2026-09-13/14 | stale |
| Old weekly bundle | `producers/build_staged_bundle_espn.py` (reads archive paths that no longer exist) | `data/weekly/staged_bundle_wk4_2026-10-03.json`; `weekly_dashboard_runs/_signals` | week 4, 2026-10-05 | stale |

Freshness rules that already exist and must be reused, not redefined:
content week vs game week and the New York clock (`pipelines/nfl_week.py`
l.3-34, SQL twin `public.nfl_content_week`); "Freshness is content vintage,
never pull time" (`docs/pipeline-rules.md` §5); `freshness_ok` and
`current / one_week_behind / stale / unknown` (`pipelines/check_reference_freshness.py`
l.113-221); import-health blocking vocabulary (`pipelines/verify_import_health.py`
l.150-171); site labels "Not updating / Held / Prior week / Freshness unknown /
Current" (`app/v2/v2.js` l.3500-3545, e.g. l.3516 and l.3541). Still open: PR #1022 (JEG-1180 stale
after Thu 12:00 CT) and PR #1042 (JEG-1200 `source_lateness.py`).

Missing and partial: "missing values never shown as zero" (`AGENTS.md` l.232-233,
part of the deploy gate); "A missing source value stays missing (null / absent
key). It is never converted to zero" (`docs/pipeline-rules.md` §4, l.104-112).

## 4. ECR conflict (reconciled with JEG-1198)

The ticket asks for "dated Vegas/ECR/ESPN/status inputs", and the old product
was "Vegas vs ECR". Against that:

- JEG-ECR-EXIT is Jeremy's directive that full-season ECR exits the project.
- The trade-value pipeline hard-excludes `ecr`, `vegas` and prediction markets
  as sources (`pipelines/import_supabase_references.py` l.97,
  `docs/import-health-schema.md` l.38, `docs/supabase-source-mapping.md`
  l.65-71). That rule governs trade-value sources; a sibling weekly product is
  not one of them, but no doc says so explicitly.
- JEG-1198 found FantasyPros ROS is ECR and excluded; `ranker_rankings` is ECR
  only (last ROS Sep 11). No weekly ECR producer exists.

This is a policy decision for Jeremy. The rule is not lifted here and no source
is added.

## 5. Proposed shared input contract (JEG-1195 to 1197)

One producer owns the weekly inputs; Versus Vegas, the waiver board and Bench
Churn only read it.

- **Artifact:** `data/weekly/inputs-wk{N}.json`, schema `weekly-inputs-v1`.
  One row per numeric `player_key` (resolved by `PlayerIndex`; unmatched rows
  kept with `player_key: null` and a reason, never guessed).
- **Legs per row:** `espn_weekly` (std/half/ppr), `status` (Sleeper status,
  injury, practice, depth), `bye`, and slots for `vegas` and `consensus` that
  stay `null` with `state: "unavailable"` until a producer exists.
- **Per leg meta (once, at the top):** source, `content_week` (Tuesday flip),
  `game_week` (Thursday flip, only for slate fields), `content_vintage`,
  `captured_at`, `state` in the existing `current / one_week_behind / stale /
  unknown` vocabulary, and `label` in `published / previous-season / modeled /
  stale / unavailable`.
- **Missing and partial:** missing is `null` plus `missing_reason`; partial keeps
  the archived provenance values (`complete`, `td-filled`, `partial`) and stays
  visible and unflagged; no zero fill, including deltas.
- **Owner boundary:** JEG-1195 owns the producer and schema; JEG-1196 owns the
  priced waiver-board artifact built on it; JEG-1197 reads that board. Waiver
  lines come from `pipelines/lib/roster_convention.py` `waiver_line()` (l.165),
  per `AGENTS.md` l.268 (JEG-556), not from a ported boundary.

## 6. Slices, readiness and file ownership

| Slice | What | Files (new unless noted) | Depends on | Ready? |
|---|---|---|---|---|
| S1 | Contract doc + JSON schema + fixture test | `docs/weekly-inputs-contract.md`, `tests/test_weekly_inputs_contract.py`, Makefile test line | none | Ready (no math, no fetch) |
| S2 | Producer from stored inputs only (ESPN weekly CSV, status history, byes, `nfl_week`) | `pipelines/build_weekly_inputs.py`, test | S1 | Ready (no new fetch; a schedule needs Jeremy's yes) |
| S3 | Vegas leg producer (port PropLine collector + `engine/vegas.py` translation, keyed on `player_key`) | `producers/`, workflow, secret | Decisions 1 and 2, a PropLine key | Blocked |
| S4 | Versus Vegas compute (disagreement, play gate) | `pipelines/` | S3, Decision 1, T1 review of the ported math | Blocked |
| S5 | Versus Vegas page with URL-persisted scoring/position filters | `app/` (replaces `weekly_vegas/dashboard/index.html`; updates `tests/test_launch_front_door.py` l.59/409 and `tests/test_launch_qa_surfaces.py` l.18) | S4, design direction (JEG-1209 pending) | Blocked |
| W1 | Availability input (roster%) | `producers/` | Decision 3 | Blocked |
| W2 | Option-value layer | — | Scorer source from the old workspace, or a decision to drop it | Blocked |
| W3 | Waiver board on the shared contract and the one waiver line | `pipelines/` | S2, W1, W2 | Blocked |

No slice touches Codex-owned work (#1069, #1071, #1072, visual redesign,
Natural fit, JEG-1217, JEG-1220).

## 7. Decisions for Jeremy

1. **Comparison side of Versus Vegas** (the old one was ECR).
   A. ESPN weekly (Mike Clay model), already current and shared; rename the
   view "Vegas vs ESPN". *(Claude's pick: it is current and the project already
   moved the gates and the staged bundle to ESPN.)*
   B. A projections consensus of ESPN weekly and CBS weekly (CBS weekly is
   captured but not published).
   C. Lift JEG-ECR-EXIT for this view and bring back weekly ECR.
2. **Vegas input.** Bring back the PropLine collector (needs a key and a new
   scheduled fetch), or keep Versus Vegas parked.
3. **Waiver availability.** Bring back an ESPN roster% pull, or build the board
   without availability.

## 8. Minimum missing to recover the originals

- The old Hatch workspace sources: Vegas page bake script, `driving_prop.py`,
  the lottery scorer `score_v0.py`, and the `waiver-trends/` tree.
- A PropLine key for any Vegas leg.

Without these the rebuild follows sections 5 and 6 rather than restoring the
archived code.
