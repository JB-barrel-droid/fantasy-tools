# Health Best Practices — Muse Lane Assessment (JEG-80)

**Lane:** Muse (PM / reviewer / deployer) · **Date:** 2026-10-02 · **Repo state checked:** `fantasy-tools` @ `b71c594`
**Parent:** JEG-78 (health program 1/4). This document is the Muse lane's independent assessment; it was written without reading the Claude or Codex lane documents.

## Claim labels

Every claim below is labeled. **[E]** = established practice in data engineering / SRE. **[C]** = cited source (named). **[J]** = my judgement as the lane that reviews and deploys this project. **[U]** = unverified — stated as observed or believed, flagged plainly.

## The two non-negotiables (from JEG-78)

1. **Never show stale data or stale computes on the trade value dashboard** — or label them unmistakably, never silently.
2. **Preserve the dashboard's input flexibility** — league size, scoring, roster shape, bench share, source toggles, user inputs must keep working. Health is not bought by freezing inputs.

---

## 1. The operational view (what this lane sees that the build lanes do not)

### How deploys actually flow

Push to `main` (via `push_to_main.py` or the scheduled dashboard-push connector) → `pages.yml` GitHub Action builds and deploys to GitHub Pages → `verify_live.py` checks the live page (HTTP 200, build tag matches expected, fix markers present). Build tags are deterministic: `tv-YYYYMMDD-HHMM-<sha>` derived from HEAD commit time, not wall clock (`sync_dashboard_artifacts.py::build_tag`, verified lines 227–242). PRs get a preview build (`preview.yml`) that never deploys, with a rendered gate (`tests/rendered_gate/gate.mjs`) that fails on uncaught page errors or DDF pie ≠ 100.0 — this gate exists because a page error on every load (JEG-44) once shipped to production before any rendered check existed.

### Recurring audit findings (2026-10-01 → 2026-10-02)

**[J]** Four patterns keep returning in different clothes:

1. **Fresh stamp, old numbers.** The signature recurrence. On 2026-09-17 `players.json`'s `method_note` described a blend recipe that had already changed (verified by code read, patched in place). On 2026-10-01/02 the ESPN adjusted curve was rescaled to a stale "canonical pie" while the metadata read 2026-09-29 — byte-identical old-level numbers under a fresh stamp (codified as the rule in `docs/QA_FRAMEWORKS.md` line 71: "no output may be rescaled/pinned to a pie older than its inputs"). **[U]** The exact rescale incident is documented in QA rounds not committed to the repo; the rule and fix commits (`ee070c6`, `ce1f99b`) are verified.
2. **Guards that pass while wrong.** `fixedPieIndexed` printed "ok" on stale values; the ESPN-zero staleness check read a combo (`half_12` literally) that does not exist and printed "ok" while two sources priced a zeroed player (JEG-51, fixed with 10 discrimination tests, commit `9ccb23c`); the `sourceMapCoverage` guard hardcoded `SOURCE_KEYS.length === 9` while the registry had grown to 11, rendering "Curves unavailable" on every production load (JEG-34). A guard that asserts the current behavior without proving it catches the broken state is worse than no guard — this project's own words, proven right twice.
3. **Guards that fail while right.** The CBS ROS starter-markup check flagged a correct 1.000 ratio as a failure (JEG-68, now a 0.98–1.6 band with 11 tests); the branding guard blocked deploys over a code comment (JEG-25); a test pinned to a typo went red on `main` and blocked deploys. False positives train people to bypass the gate, which is how pattern 2 becomes permanent.
4. **Wiring-through misses.** The VORP-translation values were correct in Supabase while the chart read the old reindexed fixture (fixed via `translate_via_vorp.py`); then the `_adjusted` sections were rebuilt from the *old* raw values because the raw-value rewrite never triggered a downstream rebuild (JEG-73, fixed with `--rebuild-adjusted` + 16 ordering pairs across all 4 sources). The fix existed; the live path did not use it. This is now codified in `docs/wiring-through-process.md`.

### Signals Jeremy finds untrustworthy — and what they teach

**[J]** From repeated corrections on my own drafts: green pipelines, fresh snapshot stamps, a check printing "ok", and a claim of "working as designed" are not evidence of correctness. Evidence is: the rendered live page shows the expected build ID; the live value matches an independent recomputation; the guard fails when presented with the broken state. Every practice below is scored against that bar.

---

## 2. Data health

### 2.1 Content-vintage freshness gates, not pull-time gates

**What:** Every freshness gate measures when the *source* last changed its numbers (content vintage), never when we last downloaded them. **[E]**

**Why here:** Expert projections re-pulled byte-identical on 2026-09-17 would have passed a pull-time gate and drafted game-day content on 6-day-old experts. **[C]** This exact failure class is recorded in JEG-8's context and the game-day gate regression tests.

**Do we do it today?** **Partly.** **Yes** for ECR game-day: `weekly_vegas/pipeline/bin/game_day.py::check_ecr_gate` enforces (1) pull mtime ≥ most-recent Thu 06:00 CT **and** (2) expert content vintage ≤ 3 days (earliest byte-identical snapshot), blocking on exit 2 when vintage is undeterminable — check I ran: read lines 163 and 588, plus the 6 regression tests. **Yes** for the import chain: `build_pipeline_checkpoints.py` uses `content_vintage` (C3 >14d = bad, >7d = warn) and flags STUCK when snapshot vintage ≠ DB-latest vintage (line 429). **No** for as-published sources' own vintage (JEG-70, VORP refresh on rollover, still In Progress) and for Razzball, which is excluded from all automated freshness controls (GAP-024 in `docs/risk-register.md`).

**Cost to adopt fully:** Low — the checkpoint machinery exists; it needs vintage coverage per source, not a new system.

### 2.2 Versioned snapshot contracts with writer audit

**What:** Every snapshot carries a versioned schema; every write records who wrote it and which run. **[E]** (schema evolution discipline; SRE audit trails.)

**Why here:** Multi-writer, multi-source writes into Supabase (save_*.py writers, CI chain, manual pulls) with no other way to tell a legitimate write from a stray one.

**Do we do it today?** **Yes.** Check I ran: `docs/import-health-schema.md` defines `trade-value-import-health-v1` (versioned schema string); `pipelines/check_naming_drift.py` enforces `trade-value-naming-manifest-v1` with the `players` table as naming authority, failing closed and blocking `make validate`; `docs/SUPABASE_WRITER_AUDIT.md` defines `pipeline_write_audit` plus `_writer_identity` / `_run_id` per-row columns. 30 tests in `tests/test_import_health.py` (verified by grep count).

**Cost:** Adopted. Maintenance cost is keeping contracts versioned on change — cheap.

### 2.3 Live-vs-stored drift detection for as-published values

**What:** Periodically compare stored native values against the publisher's live page and alert on drift. **[E]** (data-quality monitoring; **[J]** the thresholds are judgement — ours are 20% of a 25-player sample moving >5%).

**Why here:** As-published sources are restated without notice; a stale native silently propagates through VORP translation into every curve.

**Do we do it today?** **Partly.** Check I ran: `pipelines/check_fantasycalc_drift.py` exists (exit 1 on drift, 2 on failure) with a standing rule that pipelines auto-rerun when live values drift, plus a daily GitHub Actions workflow (`.github/workflows/fantasycalc-drift.yml`, 6:45 AM CDT) that refreshes and re-imports on drift — but it covers FantasyCalc only. JEG-77's end-to-end fidelity check (`pipelines/check_source_fidelity.py`: freshness, fidelity, deploy-vs-live-Pages) exists as a script, but monitor surfacing and scheduling are still Backlog.

**Cost:** Low per source — the FantasyCalc checker is the template; wire it to the 30-min heartbeat and the monitor.

### 2.4 Ordering invariants as cheap corruption detectors

**What:** When a transformation should preserve order, assert `if native A > native B then output A > output B` on a handful of pairs. **[J]** — this is my standing recommendation, born from the Puka/JSN flip: per-bucket reindex scaling preserved magnitudes but flipped order, invisible to any magnitude check.

**Why here:** Indexation, reindexing, and VORP translation all rescale values; order flips are the characteristic failure, and they are cheap to test.

**Do we do it today?** **Yes.** Check I ran: `pipelines/verify_vorp_wiring.py` asserts 16 raw-vs-adjusted ordering pairs across all 4 adjusted sources (e.g. `fantasycalc_adjusted/half_12_qb1: JSN 40.0 > Puka 31.3`); `pipelines/check_source_fidelity.py::check_fidelity` checks fixture native ordering vs reindexed per (higher, lower) pairs. JEG-73 closed with all 16 passing and live-verified.

**Cost:** Adopted. Extend to every future value transformation by default.

### 2.5 No machine-local dependencies in the data path

**What:** Every pull and bake runs on infrastructure anyone on the project can re-run — CI, or a documented scheduled job — never on one person's laptop. **[J]** (12-factor / reproducible-pipeline principle, **[C]** Herzog-style: builds must not depend on a single machine.)

**Why here:** The Razzball snapshot lives on a Mac (JEG-18 merged only after the snapshot was hand-carried; GAP-030 notes the puller is absent from the repo and the row shape was inferred). ESPN/CBS/CBS ROS pulls were also flagged as machine-local (JEG-55, JEG-71). A pipe nobody else can re-run is a pipe that fails silently when that person is away.

**Do we do it today?** **No.** Check I ran: the Razzball puller named in JEG-18 (`pipelines/pull_razzball_ros.py`) does not exist in the repo (find returned nothing); the Supabase-side code has landed and `public.razzball_projections` was created 2026-10-02 but holds **0 rows** — the first real save must run on the machine holding `data/raw/sources/razzball/`, and the merge notes warn the gate reports `MISSING razzball` until it does. Risk register GAP-024 confirms Razzball is excluded from automated freshness controls. The 6-hourly chain itself runs on GitHub infra with secrets — **yes** for the chain — but the source *pulls* feeding it are the gap.

**Cost:** Medium — one puller per source, migrated to scheduled jobs with the import-health contract. JEG-18's merge precondition shows the pattern works.

---

## 3. Pipeline health

### 3.1 Fail-closed gates at every promotion boundary

**What:** Any gate that guards promotion defaults to blocking on uncertainty: missing input, stale input, undeterminable state, failed check. **[E]**

**Why here:** A fail-open promotion is how stale data reaches the public chart silently.

**Do we do it today?** **Yes.** Check I ran: `verify_import_health.py` exits non-zero on missing/stale/failed imports; the chain's `rebuild_comparison_chain.py` halts a source on the first hold or failure (partial promotion = failure); `check_naming_drift.py` blocks validation on drift; ECR vintage undeterminable blocks game day. The JEG-8 investigation confirmed runs 3–5 failed *because* the review hold fired (usatoday + fantasypros `hold`, exit 1) — the gate did its job; the bug was only that the red chain skipped the monitor-fixture sync, since fixed with `sync_monitor_fixture()` + `continue-on-error` + status-only publish on failure.

**Cost:** Adopted. The standing risk is a future lane loosening a gate to "fix" a false positive — the remedy is fixing the check (JEG-68's band), not the gate.

### 3.2 Every guard carries a discrimination test

**What:** A regression guard must be proven against a simulated broken state: the test fails on the old code and passes on the fixed code. **[J]** — this project's hardest-won rule; **partly [E]** (mutation testing literature, **[C]** e.g. Andrews et al. on mutation testing effectiveness).

**Why here:** Patterns 2 and 3 above — silent non-firing and false alarms — are both discrimination failures. The JEG-52 pool cap was "working as designed" while a discrimination test later showed it was a no-op that could drop players (JEG-67).

**Do we do it today?** **Partly.** Check I ran: the `fixedPieIndexed` harness (`tools/guard_harness.mjs`, `tests/curve_guard_harness.js`) reproduces the JEG-5 broken state; `sourceMapCoverage` uses `SOURCE_KEYS.every(...)` with discrimination proof in AGENTS.md; JEG-51 added 10 tests that fail on the old combo-scoped check; JEG-68 added 11 tests on the 0.98–1.6 band; `tests/test_rebuild_chain_workflow.py` catches 8 workflow mutations. **But** adoption is reactive — each guard got its discrimination test only after its failure. There is no standing requirement that a new guard ships with one.

**Cost:** Low per guard, medium as culture: make "discrimination proof" a merge checklist item for any new check.

### 3.3 Idempotent, deterministic builds

**What:** Re-running the pipeline on unchanged inputs produces byte-identical outputs; promotion happens only when the fixture is stale. **[E]**

**Why here:** Deterministic builds make "is this output fresh or carried forward?" answerable by comparison instead of trust.

**Do we do it today?** **Partly.** Check I ran: the workflow header states the chain only promotes when the fixture is stale; `build_tag()` derives the tag from HEAD commit time (verified lines 227–242 of `sync_dashboard_artifacts.py`), so re-syncing the same commit yields the same tag. **Unverified:** full-chain byte determinism was not independently audited; the preview workflow's pages-vs-preview parity check (JEG-31, `tests/test_preview_workflow_matches_pages.py`) covers workflow drift, not output determinism.

**Cost:** Low — a byte-compare of consecutive no-change runs would close the **[U]**.

### 3.4 Preview builds with a rendered gate before deploy

**What:** Every change renders the real page in a headless browser and fails the build on page errors or broken computed output, before it can reach production. **[E]** (shift-left testing; preview environments.)

**Why here:** JEG-44's every-load TypeError shipped to production because no rendered gate existed; JEG-47 built it.

**Do we do it today?** **Yes.** Check I ran: `.github/workflows/preview.yml` builds exactly what `pages.yml` would publish on every PR without deploying; `tests/rendered_gate/gate.mjs` loads built `dist` in headless Chromium and fails on uncaught errors or DDF pie ≠ 100.0; the parity test fails if the two workflows drift.

**Cost:** Adopted. Keep the gate's assertions tied to registries, not literals (the JEG-34 lesson).

### 3.5 Checkpoints regenerate after a successful deploy, never before

**What:** The monitor's health snapshot is generated from the deployed state, after the deploy lands. **[J]** — operational rule from the 2026-09-30 incident: a snapshot generated before the deploy reported the old failed status as current, showing stale red C9/C10 for all sources.

**Do we do it today?** **Partly.** Check I ran: the rebuild-chain workflow regenerates checkpoints post-chain and syncs `dist/modules/` on success, consistent with the rule — but the explicit rule text is **not codified in the repo's docs** (grep of `docs/pipeline-rules.md`, `docs/MODULES.md` found no match; it lives in operator memory). **[U]** whether the current workflow ordering is enforced by a test rather than by convention.

**Cost:** Near-zero — codify the rule in `docs/pipeline-rules.md` with a workflow-ordering test.

---

## 4. Dashboard health

### 4.1 Rendered-page verification is the QA target, not the pipes

**What:** QA asserts on the live rendered page — build ID, per-player completeness under every lock mode, actual numbers — not on pipeline green. **[J]** — this is the lane's most repeated redirect: "I'm saying QA the live trade value dashboard," not the pipes.

**Why here:** The pipes were green while the served page showed a stale pie, a blank chart, and "Curves unavailable."

**Do we do it today?** **Yes.** Check I ran: `verify_live.py` fetches `https://jb-barrel-droid.github.io/fantasy-tools/`, checks build tag and fix markers, exit 1 on mismatch; module-lane rules make it the done-gate for lanes 2–4; checkpoint C10 fetches the **live served JSON** and validates the expected content week (`build_pipeline_checkpoints.py` lines 567–633). Round 1 is documented in `docs/TRADE_DASHBOARD_QA_ROUND1.md`. **[U]** Round 2 (2026-10-01/02) is not committed to the repo — its findings survive only in the QA frameworks doc and operator memory.

**Cost:** Adopted. Commit the round-2 notes so the findings are auditable.

### 4.2 Temporal consistency: nothing rescaled to an older target

**What:** No output may be rescaled, pinned, or calibrated to a pie, target, or total older than its inputs. **[J]**, codified in `docs/QA_FRAMEWORKS.md` line 71.

**Why here:** The signature recurrence (pattern 1): stale carry-forward hides under fresh metadata.

**Do we do it today?** **Partly.** Check I ran: the rule is codified and the fix commits (`ee070c6`, `ce1f99b`) verified; current `_rescale_exact` rescales to the combo's **own** `index_total` pie targets (lines 296–335), not a carried-old bake. But the rule's coverage is one framework among several, and there is no standing scan that re-asserts it on every bake — the monitor's fidelity checks (JEG-77) are the vehicle and are still Backlog.

**Cost:** Low — wire the temporal-consistency assertion into the bake's own gate so it cannot regress silently.

### 4.3 End-to-end source fidelity: live publisher vs rendered numbers

**What:** Compare the publisher's live values against the dashboard's rendered numbers, inside the monitoring dashboard, on a schedule. **[E]** (synthetic monitoring.) This is the tightened bar from "your checks are not end to end."

**Why here:** Every pipe-level fidelity check can pass while the rendered number diverges (the Puka/JSN flip persisted through green pipes until a screenshot caught it).

**Do we do it today?** **Partly.** Check I ran: `pipelines/check_source_fidelity.py` implements the three checks (freshness, fidelity, deploy-vs-live-Pages); JEG-77 carries monitor surfacing and scheduled runs and is **Backlog**. The Scale Agreement section on the module monitor (a permanent re-running verdict, not ad hoc analysis) is the closest live instance — **yes** for that one check.

**Cost:** Low-medium — the script exists; it needs scheduling and a monitor card.

### 4.4 The monitor shows checkpoints explicitly, with remediations

**What:** A status surface shows every component and sub-component, keeps DB-latest vs snapshot checkpoints separate, runs a STUCK lag timer, and each alert names the exact remediation. **[J]** — Jeremy rejected the first monitor twice for lacking this structure.

**Do we do it today?** **Partly.** Check I ran: `modules/dashboard.html` shows the fleet of 10 checkpoints × sources, per-source cards, the ESPN-zero staleness card, chain-banner crash protection, and warn/yellow status pills; the fleet counter tallies top-level sections so a bad section cannot hide. **Not yet:** checkpoint `reason` strings describe the fault but I found no explicit "run X to fix" remediation commands in the dashboard; the literal "L2" staleness naming appears only in `docs/pipeline-rules.md` for import-health layering, not on the dashboard itself.

**Cost:** Low — remediation text is a presentation pass over data the checkpoints already emit.

### 4.5 Rendered labels reflect content state, never silent blanks

**What:** Stale or paused sections are greyed with plain-language explanations; fresh and stale are visually distinct; nothing silently blanks or silently shows old numbers. **[J]** — the definitions/sources/manipulation honesty layer is the product's most distinctive feature and belongs in this discipline.

**Why here:** Non-negotiable 1 allows labeled staleness; silence is the violation.

**Do we do it today?** **Partly.** The 2026-09-17 stripped publish did exactly this (dataset-status panel, stale sections greyed with explanations, Full PPR default) — but as a one-off publish, not a standing mechanism. The dataset-status panel emits the right metadata (`meta.dataset_status` with completeness, freshness, stale flags); whether every bake surfaces it automatically is **[U]** from my checks.

**Cost:** Low — the metadata exists; bind it to rendering by default in the page shell.

### 4.6 Input flexibility is never the price of health (non-negotiable 2)

**What:** Every health measure above must work with league size, scoring, roster shape, bench share, source toggles, and user inputs intact. **[J]** — a constraint, not a practice: any proposal that freezes an input to make a check pass is rejected.

**Do we do it today?** **Yes.** Check I ran: the bench-share slider is live with the feasible interval re-solved per position; scoring and league selectors shipped with the 2026-09-17 publish; the fresh VORP wiring preserved all 12 combos. The JEG-69 sibling check (direction check brittle at non-default shapes) shows the failure mode this constraint guards against — and it is tracked as an open issue, not waived.

**Cost:** Ongoing vigilance; zero marginal cost when guards are written shape-agnostic from the start (see 3.2).

---

## 5. Top adoption priorities (judgement)

Ordered by risk reduction per unit effort, **[J]**:

1. **Finish JEG-77** — schedule the end-to-end fidelity checks and surface them on the monitor. It is the only practice that would have caught the signature recurrence (fresh stamp, old numbers) before a screenshot did.
2. **Move the source pulls off local machines** (JEG-18 pattern, JEG-55, JEG-71) — every machine-local pipe is unmonitored by construction; GAP-024 says so explicitly.
3. **Make "discrimination proof" a merge requirement** for every new check — the reactive pattern (guard fails → test added) has worked, but the next silent non-firing is already in the codebase somewhere.
4. **Codify the post-deploy checkpoint rule** in `docs/pipeline-rules.md` with a workflow-ordering test — one-line fix for a real incident class.
5. **Close the JEG-70 staleness window** — schedule the VORP translation refresh on rollover so translated values cannot go stale while natives move.
