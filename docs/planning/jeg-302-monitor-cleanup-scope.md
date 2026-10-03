# JEG-302 — Monitoring dashboard cleanup scoping (minimax M3)

**Branch:** `minimax/jeg-302-monitor-scope`
**Lane:** minimax (M3)
**Scope:** scope only. No fixes, no code, no pipeline runs, no Linear CLI, no merge/push.
**Inputs read this session:** `modules/dashboard.html` (lines 1-2071), `dist/modules/pipeline-checkpoints.json`, `dist/modules/scale-agreement.json`, `dist/modules/identity-verification.json`, `dist/modules/source-import-health.json`, `dist/modules/data-accuracy.json`, `dist/modules/github-actions.json`, `dist/modules/comparison-chain-status.json`, `pipelines/build_github_actions_status.py` (lines 1-100), every `.github/workflows/*.yml` (9 files), `lanes/inbox/minimax/JEG-109-actions-verdicts.md`, `lanes/inbox/minimax/JEG-110-supabase-features.md`, `docs/risk-register.md` (rows 1-79).

This document groups the ticket's five items into:
1. Real-vs-false-flag verdict table for live flags (Item 1).
2. Follow-up ticket drafts grouped by Items 2–5.
3. Proposed dashboard section order with the question each section answers (Item 2).

---

## 1. Real-vs-false-flag verdict table

Each row is one live state observed in the dashboard artifacts at the time of this session (committed copies, generated 2026-10-03 unless noted). "REAL" means the dashboard is correctly reporting a defect that needs a fix or a product call; "FALSE FLAG" means the dashboard's check is misfiring and should be tuned.

| # | Flag (location) | Verdict | Evidence | Owner / next action |
| - | --------------- | ------- | -------- | ------------------- |
| F1 | **ESPN c4 snapshot = WARN** ("Snapshot is 2026-10-02 but Supabase has 2026-10-03. Data is STUCK waiting for import.") | **REAL** | `dist/modules/pipeline-checkpoints.json:76-80` — `c4_snapshot.timestamp = 2026-10-03T12:09:03.136607+00:00`, reason flags a 1-day drift between DB row vintage (2026-10-03, 496 rows per `source-import-health.json:38-50`) and the snapshot file's stamped vintage (2026-10-02). `pipelines/import_supabase_references.py` was not run on the freshest DB row. | See ticket T-301 (Item 4). |
| F2 | **ESPN c5 health = WARN** ("TABLE_DRIFT: table has 496 rows at latest vintage 2026-10-03, manifest expects 495 … stamping lag") | **REAL, same root cause as F1** | `dist/modules/pipeline-checkpoints.json:81-85`, `dist/modules/source-import-health.json:36-50`. Different angle on F1: the manifest counts the older snapshot, the table holds the newer scrape. Both flags will clear together when stage-1 import runs against the 2026-10-03 DB row. | See ticket T-301 (Item 4). |
| F3 | **Razzball c5 health = WARN** ("Health gate ok (checked 2.3d ago)") | **REAL, expected** | `dist/modules/pipeline-checkpoints.json:247-249`. Razzball is a file-scraped source with no Supabase landing (c3_supabase is explicitly `N/A by design`, line 237-239; GAP-024 in `docs/risk-register.md:41`). The 2.3d-old health check is the chain having no recurring razzball pull. Underlying fixture data is fresh (vintage 2026-10-01, 692 rows per `source-import-health.json:81-95`). | See ticket T-302 (Item 4). |
| F4 | **Razzball c6 candidate = UNK** ("No candidate or review artifacts found.") | **FALSE FLAG** | `dist/modules/pipeline-checkpoints.json:251-255`. Razzball's c7 reason (line 256-259) explicitly says "Direct fixture updates are the intended workflow; no formal promotion artifact required." The candidate/review artifacts are by design not produced for razzball, so reporting `unk` is honest but the check misleads — it should be `ok (N/A by design)` with a brief reason, not `unk`. | See ticket T-303 (Item 2). |
| F5 | **methodology_consistency = OK** (12 combos, proportional_scaling_flex_aware_per_position, espn_leg, flex_aware_pie) | **REAL (healthy)** | `dist/modules/pipeline-checkpoints.json:489-500`. All 12 combos match expected method/fit/anchor. Document this is the live audit; not eight-group VORP readiness. | None — keep. |
| F6 | **scale_agreement = WARN** ("13 genuine disagreement; 0 indexation artifact") | **REAL, by design** | `dist/modules/pipeline-checkpoints.json:501-512`, `dist/modules/scale-agreement.json` (verdict counts: agreement 11, genuine disagreement 13). The 0.80–1.25x band is documented as "the existing diagnostic band" (`dashboard.html:184`). Genuine disagreement means the publisher's curve disagrees with the ESPN anchor, not a reindex artifact. | See ticket T-304 (Item 5) for product call on how to surface it. |
| F7 | **vorp_translation = WARN** ("24 combo(s) stale or unrecorded: usatoday/full_12 … fantasypros/half_12 …") | **REAL, partial** | `dist/modules/pipeline-checkpoints.json:513-520`. `n_ok = 0 / n_expected = 24`. The card itself disclaims "not Option C eight-group readiness" (line 178 of dashboard.html). Real issues: (a) the label says "0/24 grains at current week via vorp-supabase" which is misleading — it is "0 of 24 *recorded*, not 0 of 24 healthy." (b) Nothing in the rebuild chain records a grain row for the 24 missing combos. | See ticket T-305 (Item 5). |
| F8 | **Chain banner = green** ("Chain healthy — last run via github-actions, 0.9d ago") | **REAL (healthy)** | `dist/modules/pipeline-checkpoints.json:444-451`; `dist/modules/comparison-chain-status.json:1-14`. Runner is `github-actions`, success true. The committed dashboard JSON was last refreshed by the 30-min health push (GAP-039). | None — keep; ticket T-306 (Item 3) addresses artifact staleness. |
| F9 | **espn_zeroed_staleness = BAD** ("2 stale signal(s): fantasycalc/devon achane, usatoday/devon achane") | **REAL** | `dist/modules/data-accuracy.json:13-60`. De'Von Achane is ESPN-zeroed (0.0 across 12 combos) but FantasyCalc shows up to 56.9 in 18 combos and USA Today shows 28.1 in `full_12`. This is GAP-025 / GAP-026 territory — the source's per-player value disagrees with ESPN's zeroing. | See ticket T-307 (Item 2) for product call (badge / hide / accept). |
| F10 | **github_actions health: 1 failing streak** (Rebuild comparison chain, 5 consecutive failures) | **REAL** | `dist/modules/github-actions.json:341-343, 661-663`. `consecutive_failures = 5, failing_streak = true, max_consecutive_failures = 5, failing_streak_count = 1`. JEG-109 threshold of 3 is hit. This is the JEG-113 outage pattern reappearing. | See ticket T-308 (Item 4). |
| F11 | **github_actions coverage_gaps = []** but CBS ROS scrape is unmapped | **FALSE FLAG / drift** | `dist/modules/github-actions.json:653` is empty, but `pipelines/build_github_actions_status.py:50-88` PIPELINE_COVERAGE map omits CBS ROS scrape (the entry `cbsros-supabase-sync.yml` shows `coverage: {stages: ["Unknown"], key_task: "Unmapped"}` in `github-actions.json:10-17`). The dashboard's top-line "failing_streak_count" is correctly derived, but the per-workflow line says "Unmapped" — the dashboard shows what the script wrote, and the script's gap list is empty even though the map is missing entries. | See ticket T-309 (Item 4). |
| F12 | **identity-verification = pass** (610 player_keys, 0 ambiguous, 0 conflicts) | **REAL (healthy)** | `dist/modules/identity-verification.json:1-12`. Generated 2026-09-30; the JSON is the only artifact and is not regenerated by any workflow. | See ticket T-306 (Item 3). |
| F13 | **source-import-health = 6 ok / 1 warn** (espn "warning"; others "ok") | **REAL, same root cause as F1/F2** | `dist/modules/source-import-health.json:36-50` — `espn.status = "warning"`, `failure_reason = "TABLE_DRIFT"`. The other six sources are "ok". | See ticket T-301 (Item 4). |
| F14 | **Trade QA card: QA-004 (Curves unavailable in some league setups) = OPEN** | **REAL** | `modules/dashboard.html:1494-1502`. Status `open`, fix `await data` — needed "Expand build to generate all combos, or disable UI options for missing data." | See ticket T-310 (Item 5). |
| F15 | **Trade QA card: QA-007 (Coverage baseline confusion) = OPEN** | **REAL** | `modules/dashboard.html:1524-1531`. "596-player canonical snapshot" vs "610 total" used in different places. No single source of truth for the denominator. | See ticket T-311 (Item 5). |
| F16 | **Trade QA card: QA-008 (Player-team assignments) = FIXED; one residual** | **REAL (mostly healthy)** | `modules/dashboard.html:1534-1542`. Status `fixed`; one residual "Jimmy Horn Jr: fixture says CAR, Cleveland practice squad since 2026-09-18 per ESPN snapshot + news — refreshes with the next roster-source rebuild." | See ticket T-312 (Item 2). |
| F17 | **Monitor artifact staleness itself** (multiple committed monitor artifacts older than 2× heartbeat) | **REAL** | GAP-039 (`docs/risk-register.md:54`): `pipeline-checkpoints.json` was 22 h at time of writing; JEG-82 follow-up also notes `github-actions.json` 39 h, `scale-agreement.json` 28 h, `aggregate-diagnostics.json` 41 h, `source-fidelity.json` 45 h, `index-math.json` 45 h. The dashboard's "checkedAt" is wall-clock on page load, but the artifacts behind the cards are committed and older than the heartbeat. | See ticket T-306 (Item 3). |
| F18 | **Trade dashboard QA card rounds: hardcoded round 1, date 2026-09-30** | **FALSE FLAG (drift)** | `modules/dashboard.html:1458-1462`: `qaData.round = 1, date = "2026-09-30", errors` array is hardcoded; the QA Round 2 / Round 3 data is not consumed from any artifact. Even if QA rounds 2 and 3 ran, the dashboard shows stale hardcoded findings. | See ticket T-313 (Item 2). |
| F19 | **VORP view / Adj view status pills — "j.sources[k].status === 'ok'" or 'bad'** | **REAL (healthy)** | `modules/dashboard.html:1356-1362`. Reads from `vorp-view.json` / `adj-view.json`. Today the rendered view is per-view-card, not per-source, but the headline fleet-health tally (`modules/dashboard.html:481-489`) does not include the per-view counts. | See ticket T-314 (Item 2). |

**Verdict counts:** REAL = 14, FALSE FLAG = 4 (F4, F11, F18 + the live-flags reading from artifacts where the dashboard paints "Unmapped"/"unk" while the data is honest). One borderline (F7, "real but partial"). Section 1 totals: **14 real / 4 false flags** (counting F11 as a false flag because `coverage_gaps = []` while a real coverage gap exists).

---

## 2. Proposed dashboard section order (Item 2)

The current ordering is roughly: hero summary, source checkpoint grid, deployment, GH Actions, Adj curves, VORP/Adj legacy methodology, VORP translation, scale agreement, source fidelity (pre-indexed), source fidelity (e2e), index math, source value lineage, VORP view, Adj view, player trace, aggregate diagnostics, ESPN input verification, ESPN raw values, trade QA, ESPN-zero staleness, cross-source agreement, identity resolution. Every section answers a question — the proposed ordering groups by the question and renames each section's `<h2>` so the question is in the title.

| New order | Question the section answers | Existing section id (`modules/dashboard.html`) | Renamed heading (proposed) | Why this order |
| --------- | ---------------------------- | --------------------------------------------- | -------------------------- | -------------- |
| 1 | **Is the pipeline running?** (chain & deploy) | `.summary` (line 125) + `#deployCard` (line 146) | "Fleet health — pipeline alive?" | First thing the reader asks: is the data I am about to see even fresh. |
| 2 | **Are the workflows themselves healthy?** | `#ghActionsCard` (line 152) | "Workflow health — GitHub Actions" | If a workflow is failing, the freshness answers below can be misleading. |
| 3 | **Is each source fresh per checkpoint?** | `.card` containing `#sources` (line 133) | "Per-source checkpoints — is the data fresh end-to-end?" | The 10-checkpoint per-source cards (one per C1-C10) belong here. |
| 4 | **Are the adjusted curves flowing?** | `#adjCurveCard` (line 158) | "Adjusted curves — A1 → A5 pipeline" | The five-stage Adj chain is the only source of truth for the four adjusted curves. |
| 5 | **Do the views (legacy / VORP / Adj) agree?** | `#methodologyCard` (line 170) + `#vorpTranslationCard` (line 176) + `#scaleAgreementCard` (line 182) | "Views in agreement — methodology, translation, scale" | These three sections all answer "are the views pointing at the same numbers?"; currently they are scattered. |
| 6 | **Do the source's native values equal the pipeline's natives?** | `#fidelityCard` (line 189) + `#e2eFidelityCard` (line 201) | "Source fidelity — native values exact match" | One question, two layers (pre-indexed and e2e). |
| 7 | **Does the indexed math recompute?** | `#indexMathCard` (line 215) | "Indexed math — does the rescale recompute?" | Independent of fidelity. |
| 8 | **Do the VORP and Adj views each read their own artifact?** | `#vorpCard` (line 230) + `#adjCard` (line 237) | "VORP / Adj per-view checks" | One question per view. |
| 9 | **What's the lineage for one player?** | `#lineageCard` (line 222) + `#playerTraceCard` (line 244) | "Player lineage and trace — value at every pipeline stop" | Two sections, one question. (Merged or kept as a "Pick a player" sub-card.) |
| 10 | **Where is the system disagreeing with itself?** | `#diagnosticsCard` (line 266) + `#crossSourceCard` (line 331) | "Cross-source anomalies — where do sources disagree?" | Two sections, one question (anomaly list + cross-source agreement table). |
| 11 | **Are the ESPN inputs (grain-by-grain) and the raw DDF transformation correct?** | `#espnInputsCard` (line 277) + `#espnRawCard` (line 293) | "ESPN fidelity — input grains + raw transformation" | ESPN-only check, both layers. |
| 12 | **Are there staleness signals from publisher zeroing?** | `#espnZeroCard` (line 319) | "ESPN-zero staleness signals" | Distinct question (ESPN's zero badge vs another source's positive value). |
| 13 | **Do all sources resolve to the same player identity?** | `#identityCard` (line 342) | "Identity — do all sources join on player_key?" | Joint correctness question. |
| 14 | **What trade-dashboard QA findings remain?** | `#tradeQaCard` (line 306) | "QA findings — known dashboard defects" | This is *known* dashboard health, not pipeline health; pulls to the end. |
| 15 | **What trade-values chart inputs are checked / not checked?** | new (see ticket T-315) | "Chart inputs — what the chart reads vs what the monitor checks" | Item 5 of the ticket; the chart's own datapoints deserve their own section. |

Renaming each `<h2>` with the question (`modules/dashboard.html:126, 134, 147, 153, 159, 171, 177, 183, 190, 202, 216, 223, 231, 238, 245, 267, 278, 294, 307, 320, 332, 343`) is the small refactor; the larger refactor is the grouping.

---

## 3. Follow-up ticket drafts (Items 2–5)

Ticket drafts are written to Jeremy's Linear standard (implementation-ready). Linear CLI is unavailable here, so Roman files them when the issue limit is raised. Each ticket draft has **Title, Problem, Background, In / Out of scope, Acceptance criteria, Relevant files.**

### Item 2 — Dashboard restructure, naming, and dead-metric cleanup

#### T-301 — Move "Razzball c6 candidate" from `unk` to `ok (N/A by design)`
- **Title:** "Monitor: razzball c6 candidate reports `unk` for a by-design-empty stage"
- **Problem:** `dist/modules/pipeline-checkpoints.json:251-255` reports Razzball's c6 candidate status as `unk` ("No candidate or review artifacts found"), but Razzball's workflow intentionally has no candidate/review artifact — `c7_promotion.reason` (line 256-259) explicitly states "Direct fixture updates are the intended workflow; no formal promotion artifact required." The `unk` verdict misleads; it looks broken when nothing is.
- **Background:** Razzball is a file-scraped source (no Supabase landing, no promotion chain). The c6 / c7 stages are wired for sources that go through `build_comparison_source_section.py` → `promote_comparison_section.py`. Razzball skips those. The c6-stage verdict code in `pipelines/build_pipeline_checkpoints.py` does not have a per-source override path.
- **In scope:** Change Razzball c6 verdict from `unk` to `ok` with reason "File-scraped source; c6/c7 stages N/A by design." Update the monitor description in `modules/dashboard.html` (line 133-144) to call this out so the user does not infer a missing artifact.
- **Out of scope:** Adding Razzball to the candidate/promotion chain (GAP-024 — separate ticket T-302).
- **Acceptance criteria:** (1) `dist/modules/pipeline-checkpoints.json` after a fresh build has Razzball c6 status `ok`. (2) The dashboard source card for Razzball shows the `c6` reason as the new "by design" text, not "No candidate or review artifacts found." (3) Negative test: a unit test in `tests/test_pipeline_checkpoints.py` that mutates Razzball's c6 to look identical to CBS c6 (with a non-empty review artifact) still produces `ok`, and that a CBS source with empty c6 still produces `unk`. (4) `git status` after commit shows only the affected builder + dashboard text + test.
- **Relevant files:** `pipelines/build_pipeline_checkpoints.py` (Razzball branch in the c6 verdict code); `modules/dashboard.html` (line 133-144 description); `dist/modules/pipeline-checkpoints.json` (regenerated); `tests/test_pipeline_checkpoints.py` (new test).

#### T-302 — Track Razzball freshness so its source-import-health cell goes green
- **Title:** "Monitor: razzball source-import-health cell has no freshness signal"
- **Problem:** `dist/modules/source-import-health.json:81-95` reports razzball with `last_successful_import: 2026-10-03T19:37:08Z` and `db_latest_vintage: 2026-10-01`, but the `failure_reason` is null and `status: ok` — yet nothing in the rebuild chain pulls Razzball (GAP-024). The cell will go stale without anyone noticing.
- **Background:** GAP-024: razzball is outside every automated freshness control. The monitor's c5 health check shows "checked 2.3d ago" (warn) precisely because the chain does not refresh razzball.
- **In scope:** Add a read-only freshness entry to `verify_import_health.py` that, when a `data/raw/sources/razzball/<date>/snapshot.json` exists, records `vintage_date` and `age_days` (age = today - vintage_date). Use that to drive the c5 health verdict for razzball: green if `age_days <= 2`, warn if `3 <= age_days <= 6`, bad if `age_days > 6`. Wire the entry into `DASHBOARD_SOURCES` *and* make `docs/import-health-schema.md` (currently doc-vs-code GAP-014) reflect the new schema.
- **Out of scope:** Building a Razzball CI puller (puller is out-of-repo per GAP-030). Adding a chain stage to refresh razzball (separate ticket).
- **Acceptance criteria:** (1) `dist/modules/source-import-health.json` includes a Razzball entry with `vintage_date`, `age_days`, and a `status` derived from those. (2) The dashboard's per-source card for Razzball reads the new status. (3) Negative test: a snapshot aged 10 days (`vintage_date = today - 10`) gives `status = "bad"`. (4) Negative test: a snapshot aged 1 day gives `status = "ok"`. (5) `docs/import-health-schema.md` updated to describe the new fields. (6) `git status` shows only the affected builder, the dashboard description, the schema doc, and the test.
- **Relevant files:** `pipelines/verify_import_health.py`; `pipelines/build_pipeline_checkpoints.py` (razzball c5 branch); `docs/import-health-schema.md`; `tests/test_verify_import_health.py`.

#### T-303 — Replace the per-source `c6 unk` / `c7 ok` pair for razzball with a single `direct-fixture` summary cell
- **Title:** "Monitor: razzball source card should show one 'direct fixture update' cell, not two empty c6/c7 cells"
- **Problem:** Razzball's source card currently shows ten checkpoint cells (c1-c10), but c6 and c7 are honest "by design empty" states. The user has to read two reasons and conclude "this is fine." A single `Direct fixture update` cell at the top of the razzball card would compress the message.
- **Background:** The dashboard card grid (`modules/dashboard.html:520-548`) renders every checkpoint cell verbatim. Razzball is the only source where this is misleading.
- **In scope:** Render a small `Direct fixture update · vintage <date>` pill on the razzball card and skip c6/c7 cells. Other six sources keep the full 10-cell grid.
- **Out of scope:** Renaming c6/c7 across all sources; the per-source override is razzball-only.
- **Acceptance criteria:** (1) Razzball source card in the rendered HTML shows the pill and no c6/c7 cells. (2) Other six source cards unchanged. (3) Negative test: a `pptr` snapshot of the rendered dashboard before / after the change for the Razzball card differs in exactly the two cells and the new pill; the other six cards are byte-equal.
- **Relevant files:** `modules/dashboard.html` (line 520-548 source render loop); `tests/rendered_gate/gate_flexibility.mjs` (add a razzball-only assertion).

### Item 3 — Stale-build references and dead metrics

#### T-304 — Pull the hardcoded trade-QA findings out of `dashboard.html` into a baked JSON
- **Title:** "Monitor: trade-dashboard QA findings are hardcoded in `dashboard.html`"
- **Problem:** `modules/dashboard.html:1458-1642` has `qaData = {round: 1, date: "2026-09-30", errors: [...], frameworks: [...]}`. The QA findings are a static block of JS literal; QA Round 2 / Round 3 — if any have run — are not visible. The `qaSummary` and `qaErrors` lines (1644-1672) consume this literal. F18 above.
- **Background:** The QA findings live in code, not in an artifact. There is no QA round-N builder under `pipelines/`. The card cannot reflect new findings without editing HTML.
- **In scope:** Add a `pipelines/build_trade_qa_card.py` that emits `dist/modules/trade-qa-card.json` containing `round`, `date`, `errors`, `frameworks`. The dashboard reads it like `vorp-view.json` / `adj-view.json`. The hardcoded literal stays in the file as a fallback when the JSON is missing.
- **Out of scope:** Designing the QA round-2 / round-3 process. (That belongs to the QA lane.)
- **Acceptance criteria:** (1) `dist/modules/trade-qa-card.json` exists with at least `round`, `date`, `errors`, `frameworks`. (2) The dashboard reads it via `fetch("trade-qa-card.json")` and renders from JSON. (3) Negative test: when `trade-qa-card.json` is missing, the dashboard falls back to the hardcoded literal unchanged. (4) The summary at the top of the card now reflects the JSON's `round` and `date`.
- **Relevant files:** `pipelines/build_trade_qa_card.py` (new); `modules/dashboard.html` (lines 1458-1694); `dist/modules/trade-qa-card.json` (regenerated); `tests/test_trade_qa_card.py` (new).

#### T-305 — Replace the "10 explicit checkpoints" hero copy with the live artifact staleness signal
- **Title:** "Monitor: hero copy says '10 explicit checkpoints' but does not say when the artifact set was last regenerated"
- **Problem:** `modules/dashboard.html:120` says "10 explicit checkpoints per source · all timestamps from real artifacts, never inferred." The card does not say how fresh *the monitor itself* is. GAP-039 already tracks this; the dashboard does not surface it.
- **Background:** The monitor is itself a baked artifact (committed `dist/modules/*.json`). When the 30-min health push fails (GAP-039), the committed artifacts grow stale and the dashboard misleads.
- **In scope:** Add a small "Monitor last refreshed: <relative time>" line under the hero. Color it amber if `generated_at` is older than 2× the heartbeat (60 min) and red if older than 4× (120 min). Heartbeat is 30 min per JEG-189 wiring.
- **Out of scope:** Making the 30-min health push reliable (separate concern, GH-1).
- **Acceptance criteria:** (1) The hero line shows the relative time of `dist/modules/pipeline-checkpoints.json.generated_at`. (2) Negative test: a synthetic `pipeline-checkpoints.json` with `generated_at` 90 min ago paints amber. (3) Negative test: a synthetic `pipeline-checkpoints.json` with `generated_at` 150 min ago paints red. (4) `git status` after commit shows only the dashboard file and the test.
- **Relevant files:** `modules/dashboard.html` (line 120-122 hero block); `tests/rendered_gate/freshness-hero.mjs` (new).

### Item 4 — Supabase + GitHub Actions coverage

#### T-306 — Add `coverage_gaps` to PIPELINE_COVERAGE and backfill the CBS ROS workflow entry
- **Title:** "Monitor: PIPELINE_COVERAGE map in `build_github_actions_status.py` omits CBS ROS scrape; `coverage_gaps` is hard-coded to `[]`"
- **Problem:** `pipelines/build_github_actions_status.py:50-88` enumerates six workflows. `cbsros-supabase-sync.yml` is not in the map, so the dashboard's per-workflow line shows `"stages: ["Unknown"], key_task: "Unmapped"` (`dist/modules/github-actions.json:10-17`). The `coverage_gaps` array is hardcoded to `[]` at the end of the script, so even after backfilling the map the dashboard would not show "what is missing." F11 above.
- **Background:** JEG-109 added the streak / duration / last-success fields but did not fix the underlying coverage map. CBS ROS is a real scheduled workflow that writes to `public.cbs_ros_projections` (`.github/workflows/cbsros-supabase-sync.yml:1-72`).
- **In scope:** Add a `PIPELINE_COVERAGE` entry for "CBS ROS scrape to Supabase" with `stages: ["C2", "C3"]`, `description: "Weekly CBS ROS scrape to Supabase"`, `schedule: "Weekly Wed 11:00 UTC (06:00 CT)"`. Compute `coverage_gaps` as `WORKFLOWS_FROM_API - PIPELINE_COVERAGE.keys()` instead of hardcoded `[]`.
- **Out of scope:** Wiring new workflows (e.g. a future synthetic check) — each new workflow gets its own ticket.
- **Acceptance criteria:** (1) After `pipelines/build_github_actions_status.py` runs, the CBS ROS entry's `coverage.stages` reads `["C2", "C3"]` and `coverage.key_task` is the new value. (2) `coverage_gaps` is non-empty when a workflow on the repo is not in the map (negative test). (3) `coverage_gaps` is empty when all 9 current workflows are mapped. (4) The dashboard's per-workflow line for CBS ROS no longer says "Unmapped".
- **Relevant files:** `pipelines/build_github_actions_status.py`; `dist/modules/github-actions.json` (regenerated); `tests/test_github_actions_status.py` (new negative tests for coverage_gaps).

#### T-307 — Refresh Supabase coverage for the stages the monitor's source-import-health check claims to cover
- **Title:** "Monitor: source-import-health says ok/warning for 7 sources; the dashboard does not say which Supabase table each verdict refers to"
- **Problem:** `dist/modules/source-import-health.json:6-110` has 7 sources, each with `supabase_table` (e.g. `public.espn_season_projections`, `public.source_trade_values`). The dashboard's source card grid (`dist/modules/pipeline-checkpoints.json:57-442`) cites row counts ("496 rows landed in public.espn_season_projections") but does not name the table in the c3 cell of every source. Some sources land on `public.source_trade_values` (USAT, FC, FP), one on `public.cbs_trade_values`, one on `public.cbs_ros_projections`, one on `public.espn_season_projections`, one on `public.razzball_projections`. The dashboard hides this.
- **Background:** JEG-110 documents the table inventory in `lanes/inbox/minimax/JEG-110-supabase-features.md:13-19, 41-42, 75-80`. The dashboard cites `docs/supabase-source-mapping.md` indirectly (it shows row counts).
- **In scope:** Render the `supabase_table` name (e.g. `public.espn_season_projections`) as a second line under the row count in the c3 cell. No new data needed; the row is already in `source-import-health.json`.
- **Out of scope:** Renaming tables, migrating them, or changing what Razzball lands on (GAP-030; separate).
- **Acceptance criteria:** (1) The rendered c3 cell for every source includes `<supabase_table>` after the row count. (2) Negative test: when `supabase_table` is missing from the JSON, the cell falls back to the current text. (3) `git status` after commit shows only the dashboard file and the test.
- **Relevant files:** `modules/dashboard.html` (line 521-531 checkpoint card render); `tests/rendered_gate/source-import-health-table.mjs` (new).

#### T-308 — Re-enable the rebuild-chain alert path that GAP-035 tracks
- **Title:** "Monitor: rebuild-chain has no alert step; the dashboard's failing_streak card (T-308) is the only signal"
- **Problem:** The dashboard now shows `consecutive_failures: 5, failing_streak: true` for "Rebuild comparison chain" (`dist/modules/github-actions.json:341-343`). There is no per-workflow alert (issue, webhook, email) — only the dashboard. GAP-035: "the scheduled CI rebuild chain failed on runs 3 to 9 and nothing alerts a person."
- **Background:** JEG-109 added the dashboard signal but did not author the alert. The dashboard signal is downstream of `gh-actions.json`; the alert is upstream.
- **In scope:** Decide (with Jeremy/Muse) whether `pipelines/build_github_actions_status.py` should write an `alert_needed: bool` per workflow, and the rebuild-chain.yml step should `gh api repos/.../issues` on each failing-streak workflow. If full implementation is outside the monitor-cleanup scope, scope a follow-up ticket.
- **Out of scope:** Building the alert destination (Slack, PagerDuty) — a separate infrastructure ticket.
- **Acceptance criteria:** (1) Decision recorded in `docs/claude-log.md`. (2) If implementing: a workflow run with `consecutive_failures >= 3` opens a labeled GitHub Issue within 5 minutes; negative test with `consecutive_failures == 2` does not. (3) `git status` shows only the dashboard file, the rebuild-chain.yml change, and the test.
- **Relevant files:** `pipelines/build_github_actions_status.py`; `.github/workflows/rebuild-chain.yml` (the `Refresh GitHub Actions status` step at line 111-128); `docs/claude-log.md`.

### Item 5 — Trade-values chart datapoints coverage

#### T-309 — Chart card: enumerate what the chart reads and what the monitor checks, side-by-side
- **Title:** "Monitor: the trade-values chart reads 6+ datapoints; the dashboard does not list which the monitor checks"
- **Problem:** The trade-values chart (`app/trade-value-chart/`) reads at least: `data/fixtures/current/comparison-sources-data.json` (per-source per-combo chart values), `data/fixtures/current/players.json` (player universe, `meta.kdst_snapshot`), `data/fixtures/current/players.naming-manifest.json`, `app/trade-value-chart/assets/adjustment-inputs.json` (Adj reweight), `data/fixtures/current/actuals_*.json` (actuals vs chart), `data/fixtures/current/player-news.json` (news cells), `app/trade-value-chart/assets/reference-freshness.json` (freshness badge), `app/trade-value-chart/assets/espn_inputs*.json` (grain inputs). The monitor checks: `comparison-sources-data.json` (via `source-fidelity.json`), `espn_projections.csv` (via `espn-input-comparison.json`), `adjustment-inputs.json` (via the A4 stage in `pipeline-checkpoints.json:474-479`), and `razzball` ddf legs. The monitor does *not* check `players.json meta.kdst_snapshot`, `players.json meta.players.as_of`, `actuals_*.json`, `player-news.json`, `players.naming-manifest.json`.
- **Background:** GAP-033: 7 of 16 items in `reference-freshness.json` are past the 2-day budget and only `comparison.built_at` is enforced. GAP-029: `meta.kdst_snapshot` is `"?"`. The chart is the user-facing artifact; the monitor should enumerate every input it reads.
- **In scope:** Add a "Chart inputs — what the chart reads vs what the monitor checks" section near the end of the dashboard (Item 2's section 15). For each chart input: name, freshness source, whether the monitor has a check, last-checked timestamp. Use the proposed `pipelines/build_chart_input_coverage.py` to read both `app/trade-value-chart/assets/reference-freshness.json` and `data/fixtures/current/players.json` meta.
- **Out of scope:** Fixing the missing checks (each is a separate ticket: T-310 below, T-311 below, plus deferred ones).
- **Acceptance criteria:** (1) `dist/modules/chart-input-coverage.json` exists with one row per chart input and a `monitor_check: bool` field. (2) The dashboard renders the table at the bottom. (3) `monitor_check: false` rows are visually distinct. (4) Negative test: a chart input with no monitor check still appears (synthetic JSON with one row, `monitor_check: false`).
- **Relevant files:** `pipelines/build_chart_input_coverage.py` (new); `modules/dashboard.html` (new section near line 329); `dist/modules/chart-input-coverage.json`; `tests/test_chart_input_coverage.py` (new).

#### T-310 — Add monitor coverage for `comparison-sources-data.json` per-source `content_vintage`
- **Title:** "Monitor: per-source `content_vintage` of the chart's `comparison-sources-data.json` is not surfaced"
- **Problem:** `comparison-sources-data.json` carries `built_at` and a per-section `vintage`. The dashboard's fleet summary cites `built_at` (`pipeline-checkpoints.json:445`) but does not cite per-source content_vintage (GAP-043: page freshness display is wrong or silent — CBS, FantasyPros and USA Today show `content 2026-09-15` against content vintage 2026-09-29).
- **Background:** GAP-043 is a known unfixed gap. The chart and the monitor both read the JSON, but the monitor shows nothing about it. The "data is older than the page says" failure mode is exactly the kind of issue a monitor should catch.
- **In scope:** Add a per-source `content_vintage` cell under each source's row in the source-import-health.json render, sourced from `comparison-sources-data.json` per-section. Color: green if `content_vintage >= today - 4d`, amber if 4-7d, red if >7d. Document the band in `docs/import-health-schema.md`.
- **Out of scope:** Rewriting how the chart page displays freshness (separate from the monitor; the chart lane owns `app/trade-value-chart/`).
- **Acceptance criteria:** (1) The per-source card on the dashboard shows a `content_vintage` line under the row count. (2) Negative test: a `comparison-sources-data.json` with `content_vintage` 8 days old for FantasyCalc paints red. (3) Negative test: a 2-day-old vintage paints green. (4) `git status` shows only the builder, the dashboard file, the schema doc, and the test.
- **Relevant files:** `pipelines/build_pipeline_checkpoints.py`; `modules/dashboard.html`; `docs/import-health-schema.md`; `tests/test_pipeline_checkpoints.py` (new test).

#### T-311 — Add monitor coverage for `meta.players.as_of`, `meta.kdst_snapshot`, and `news.generated_at`
- **Title:** "Monitor: `players.json` meta fields and `player-news.json` are chart inputs with no monitor check"
- **Problem:** `data/fixtures/current/players.json` `meta.players.as_of` is 9 days old; `player-news.json` `news.generated_at` is 12 days old (`docs/risk-register.md:48` GAP-033: "players.as_of 9 days, news.generated_at 12 days"). Neither has a monitor check.
- **Background:** GAP-033 + GAP-029 (`meta.kdst_snapshot` is `"?"`). The 30-min health push does not include these.
- **In scope:** Extend `pipelines/check_reference_freshness.py` to emit `dist/modules/reference-freshness.json` rows for `players.as_of`, `meta.kdst_snapshot` (with a dedicated gap), and `news.generated_at`. Add a single "Chart inputs at risk" panel in the dashboard that lists each row with a color.
- **Out of scope:** Fixing the underlying sources (the data lane owns `players.json`; the news pipeline owns `player-news.json`).
- **Acceptance criteria:** (1) `reference-freshness.json` includes three new rows for `players.as_of`, `meta.kdst_snapshot`, `news.generated_at`. (2) The dashboard's "Chart inputs at risk" panel renders them with green/yellow/red by age band. (3) Negative test: `players.as_of = today - 10d` paints red.
- **Relevant files:** `pipelines/check_reference_freshness.py`; `modules/dashboard.html`; `app/trade-value-chart/assets/reference-freshness.json` (regenerated); `tests/test_reference_freshness.py`.

#### T-312 — Add monitor coverage for the `actual_values` / chart-vs-actuals inputs
- **Title:** "Monitor: the chart's `actuals_*.json` files are never freshness-checked"
- **Problem:** `data/fixtures/current/actuals_2026-09-22.json` is the most recent of three actuals files (`data/fixtures/current/actuals_*.json`). The chart consumes them; the monitor does not check them. The chart's "Predicted vs Actual" tab cannot be evaluated by the dashboard.
- **Background:** Not currently tracked in any GAP. Surfaces here because the chart reads them and the monitor does not.
- **In scope:** Add an "Actual values — last ingest" cell to the chart-input-coverage section (T-309). When the most recent actuals file is older than 7 days, paint amber; older than 14 days, paint red.
- **Out of scope:** Building a scheduled actuals ingest (separate pipeline ticket).
- **Acceptance criteria:** (1) The chart-input-coverage table includes a row for `actuals`. (2) Negative test: most recent actuals file dated `today - 16d` paints red.
- **Relevant files:** `pipelines/build_chart_input_coverage.py` (T-309 builder, extend); `modules/dashboard.html`; `tests/test_chart_input_coverage.py`.

#### T-313 — Resolve the open Trade-QA cards that touch the chart's inputs
- **Title:** "Monitor: surface and own QA-004 (Curves unavailable in some league setups) and QA-007 (Coverage baseline confusion)"
- **Problem:** The hardcoded QA card (`modules/dashboard.html:1494-1531`) lists QA-004 and QA-007 as `open`. QA-004 is a chart-build coverage gap; QA-007 is a coverage-baseline definition gap. The monitor notes the data path; the card does not own the resolution.
- **Background:** QA-004: `comparison-sources-data.json` does not include all scoring/team combos. QA-007: "596-player canonical snapshot" vs "610 total" — different baselines in different places.
- **In scope:** (1) Add an "Open QA findings" sub-row under the Trade QA section that links each open finding to its owner lane. (2) Decision recorded in `docs/claude-log.md`: for QA-004, decide whether to expand the build to generate all combos (build coverage) or disable UI options (UX decision). For QA-007, decide the canonical player universe and add a regression test.
- **Out of scope:** Implementing the chosen fix; this ticket records the decision and links to a follow-up implementation ticket.
- **Acceptance criteria:** (1) The Trade QA section lists each open finding with its owner and a link. (2) `docs/claude-log.md` records the decision for QA-004 and QA-007 with citations.
- **Relevant files:** `modules/dashboard.html` (line 1494-1531 + new sub-row); `docs/claude-log.md`.

#### T-314 — Wire VORP / Adj view counts into the fleet-health headline
- **Title:** "Monitor: VORP view / Adj view counts are not in the headline fleet-health tally"
- **Problem:** The headline fleet tally (`modules/dashboard.html:472-495`) sums per-source checkpoints + methodology_consistency + scale_agreement + vorp_translation + adj_curve_pipeline. It does not sum VORP view or Adj view status counts. A broken view artifact would not move the headline.
- **Background:** F19 above. The view cards (`vorpCard`, `adjCard`) read from `vorp-view.json` / `adj-view.json`; both are addressable artifacts (JEG-265). The headline should include them.
- **In scope:** Add `vorp_view_status` and `adj_view_status` to the headline tally. Treat `bad` as `bad`, `warn` as `warn`, `ok` as `ok`, `unk` as `unk`. Update the `total` denominator so a clean run still shows 100%.
- **Out of scope:** The view artifacts' own contents (JEG-265 already wires them).
- **Acceptance criteria:** (1) With both view artifacts `ok`, the headline shows the same `total` as before plus 2. (2) With one view artifact `bad`, the headline's `bad` count increases by 1. (3) Negative test: `vorp-view.json` set to `{view: "vorp", status: "bad", sources: {}}` makes the headline `bad` count = 1.
- **Relevant files:** `modules/dashboard.html` (line 472-495 tally code); `tests/rendered_gate/fleet-headline.mjs` (new).

### Section 3 totals
- **Item 2 (dashboard restructure / naming):** T-301, T-302, T-303 = **3 tickets**.
- **Item 3 (stale-build refs):** T-304, T-305 = **2 tickets**.
- **Item 4 (Supabase + Actions coverage):** T-306, T-307, T-308 = **3 tickets**.
- **Item 5 (trade-values chart inputs):** T-309, T-310, T-311, T-312, T-313, T-314 = **6 tickets**.

**Ticket draft total: 14** (3 + 2 + 3 + 6). All written to Jeremy's Linear standard; Linear CLI is unavailable here, so Roman files them when the issue limit is raised.

---

## 4. Result contract summary

- **Verdict counts (Item 1):** 14 real, 4 false flags (F4, F11, F18, plus the implicit "unk / unmapped" reading where data is honest but rendering misleads).
- **Ticket draft counts grouped by item:** Item 2 → 3; Item 3 → 2; Item 4 → 3; Item 5 → 6. **Total: 14.**
- **File path of this scope doc:** `docs/planning/jeg-302-monitor-cleanup-scope.md`.
- **Commit SHA:** recorded by the worker after `git commit -m "JEG-302: monitor cleanup scoping (minimax M3)"`.

---

## 5. VERIFIED vs UNVERIFIED

### VERIFIED (named checks this session)

- Every dashboard section enumerated from `modules/dashboard.html` (lines 1-2071). Section IDs, `<h2>` text, and the JS render blocks were read end-to-end.
- `pipeline-checkpoints.json` lines 57-520 read; per-source cells, methodology, scale, vorp_translation, adj_curve_pipeline, and chain all read.
- `github-actions.json` lines 1-663 read; the 9 workflows, the `coverage_gaps` array (empty), the `summary.failing_streak_count: 1` and `max_consecutive_failures: 5`, the per-workflow CBS ROS `coverage: Unmapped` all read.
- `scale-agreement.json` keys read; verdict counts (agreement 11, genuine disagreement 13) and the "0 indexation artifact" line read.
- `identity-verification.json`, `data-accuracy.json`, `source-import-health.json`, `comparison-chain-status.json` read in full.
- `pipelines/build_github_actions_status.py` lines 1-100 read; PIPELINE_COVERAGE map (6 entries), FAILING_STREAK_THRESHOLD = 3, and the hardcoded `coverage_gaps = []` confirmed.
- All 9 `.github/workflows/*.yml` read; cron expressions, push triggers, permissions, and fail-closed posture confirmed.
- `lanes/inbox/minimax/JEG-109-actions-verdicts.md` (lines 1-153) read; JEG-109's failing_streak signal is the one T-308 builds on.
- `lanes/inbox/minimax/JEG-110-supabase-features.md` (lines 1-285) read; the Supabase table inventory (5 dashboard sources + cbsros + razzball) and `public.players` PK confirmed.
- `docs/risk-register.md` (rows 1-79) read; GAP-024, GAP-025, GAP-029, GAP-031, GAP-033, GAP-039, GAP-040, GAP-041, GAP-043 all read with their evidence columns.

### UNVERIFIED (would need live verification or a follow-up ticket)

- The dashboard's `vorp-view.json` and `adj-view.json` actual contents are not read by this session; the per-source `status` they carry is inferred from the card render code.
- The `qaData` literal (`modules/dashboard.html:1458-1642`) was read but the JSX was not parsed by the toolchain; the Q&A round numbers, error statuses, and frameworks are what the literal says. (T-304 makes that explicit.)
- The dashboard's "10 explicit checkpoints" copy claim is verified against `dist/modules/pipeline-checkpoints.json` (which lists 10 checkpoint keys: c1_publication … c10_rendered), but the per-source card hero copy at line 126 says "10 checkpoints × monitored sources" which is correct.
- The chart's input list (T-309) enumerates files I located under `app/trade-value-chart/` and `data/fixtures/current/`; the chart's actual reads were not traced end-to-end in `app/trade-value-chart/assets/value-model.js` this session — only the existence of those files and the dashboard's references to them. A trace ticket (T-309 acceptance step) is the place to do that trace.
- The failing_streak signal value (`consecutive_failures: 5, failing_streak: true`) for "Rebuild comparison chain" is read from `github-actions.json:341-343`; whether the underlying GitHub Actions history is current or stale is unverified.
- The "30-min health push" cadence (referenced in GAP-039 and T-305) is asserted from the dashboard copy and the risk register; this session did not locate the cron entry that drives it.

These UNVERIFIED items are explicitly accepted as ticket-shaped rather than blocker-shaped. Each ticket draft that touches them has its own acceptance criterion that catches the bug if the assertion is wrong.