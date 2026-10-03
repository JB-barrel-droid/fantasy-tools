# 05 — Critical Path, Silent Stalls, Manual Interventions, GitHub-Logs-Only State

**Phase:** JEG-285 Phase 1 (Discovery / current-state inventory)
**Method:** read every workflow + every `pipelines/pull_*.py` + `pipelines/save_*_references.py` + `pipelines/import_supabase_references.py` + `pipelines/verify_import_health.py` + `pipelines/rebuild_comparison_chain.py` + `pipelines/check_fantasycalc_drift.py` + `ops/watchdog/*` + `docs/risk-register.md` + `docs/health/claude-best-practices.md` + `docs/health/muse-best-practices.md` + `docs/claude-log.md` (2026-10-02 entry). Cross-checked every risk against the code that produces it.
**Scope:** trade-value chart cutover. `weekly_vegas/` and `waiver_wire/` risks noted only as siblings; their internals are Phase-2 territory.

The brief asks for four buckets of risk for the cutover: **critical-path datasets**, **jobs that silently stall or continue on stale inputs**, **jobs needing manual intervention**, **state that exists only in GitHub logs**. This file inventories each bucket.

---

## A. Critical-path datasets (whose staleness breaks the cutover)

A dataset is **critical-path** if (a) it is consumed by `make validate`, the GitHub Pages deploy, or the 6-hourly rebuild chain, AND (b) it has no automatic freshness enforcement that holds a deploy when it ages. These are the assets whose backplane must be moved to the Supabase-first control plane without a regression in freshness behavior.

### A1. `public.source_trade_values` — `fantasycalc / usatoday / fantasypros` (3 of 5 source-as-published)

- **Why critical** — the 6-hourly chain imports from this table on every run (`.github/workflows/rebuild-chain.yml:60–62`); `make validate`'s `make import-health` gate re-queries it (`docs/import-health-schema.md` + `verify_import_health.py:14`); the deploy path runs `make validate` (`.github/workflows/pages.yml:33–34`). If this table is empty / stale / wrong-vintage, **the chain goes red and the deploy gate can block a deploy** (`docs/risk-register.md` GAP-019 — the chain is red on record specifically because `usatoday` and `fantasypros` reviews return `hold`, not because the data is missing).
- **Backplane today** — written by `pipelines/save_*_references.py` from `ops/watchdog/ingest_*.py` on the user's machine; read by `rebuild-chain.yml` from `iskiybsimubiujwuchsl.supabase.co` via `pipelines/gh_sbclient.py`.
- **Cutover risk** — if Phase 2 moves the writer to a Supabase Edge Function / Supabase cron, the writer still needs to read from the same table with the same upsert grain (9-column bake-versioned per `sql/migrations/004_source_trade_values_bake_version.sql`). The shared unique index makes concurrent writes from the new writer + legacy writer a conflict path (GAP-023's resolution only handled the same-writer re-run case; two-writer contention is unverified).
- **File + line citations** — `sql/migrations/004_source_trade_values_bake_version.sql:22–24`, `sql/migrations/005_source_trade_values_grain_bake_aware.sql:22–23`, `pipelines/import_supabase_references.py:86–94`, `docs/risk-register.md` GAP-019 / GAP-023.

### A2. `public.espn_season_projections`, `public.cbs_trade_values`, `public.cbs_ros_projections`, `public.razzball_projections` (4 sources)

- **Why critical** — the four remaining dashboard sources. The chain imports all of them via `import_supabase_references.py:86–94` (`SOURCE_TABLES` dict). `cbs_ros_projections` has its own DDF leg path (per `rebuild_comparison_chain.py:11–16`); `razzball` is hard-excluded from automated freshness (GAP-024).
- **Cutover risk** — `razzball` is the lone source without a repo-owned puller (`risk-register.md` GAP-030 line: "the puller named in JEG-18 is not in the repo, so the real snapshot row shape is inferred, not verified"); the table was created empty on 2026-10-02 and the first real save (`692 rows`) followed. Phase 2 cannot assume a stable row shape until the puller lands in the repo.
- **File + line citations** — `sql/migrations/002_cbs_ros_projections.sql:5–28`, `sql/migrations/003_razzball_projections.sql:14–40`, `pipelines/import_supabase_references.py:86–94`, `docs/risk-register.md` GAP-024 / GAP-030.

### A3. `public.players` (canonical identity)

- **Why critical** — naming authority. Every save step resolves identity via the four-aliases map + this table (e.g. `pipelines/save_espn_cbs_references.py:25–32` "cameron ward" → "cam ward" (697), etc.). If identity reads return stale / wrong rows, every save and every match goes wrong silently because the alias map is exact-match only.
- **Cutover risk** — the table is owned outside this repo per `docs/architecture-current.md:108`. A cutover that moves writers to a Supabase EF inherits whatever ID-resolution the EF uses; if the EF ports the Python ALIASES map to a TS version, the four verified aliases must move identically.
- **File + line citations** — `pipelines/save_espn_cbs_references.py:25–32`, `pipelines/build_ddf_two_tier_leg.py:ALIASES` (imported from), `docs/architecture-current.md:108`.

### A4. `data/fixtures/current/comparison-sources-data.json` (the live fixture)

- **Why critical** — the only writer to the fixture is `promote_comparison_section.py` (per `docs/pipeline-rules.md:77–84`); the deploy path serves it from `dist/modules/` via `make sync`; every other deploy stores its `built_at` is enforced by `make freshness-check MAX_STALE_DAYS=2` (per `README.md:96–99`). A stale fixture breaks the chart; a wrong fixture breaks the chart silently.
- **Cutover risk** — Phase 2 may move the promotion trigger from `rebuild-chain.yml` to a Supabase cron; the "only writer" rule must be preserved. The promotion refuse conditions (`docs/pipeline-rules.md:79–83`: review verdict `ready`, reindexed bytes still match, fixture natives still match, candidate slugs in `player_keys`, `--approve` recorded) must be re-implemented faithfully or every promotion becomes a silent regression.
- **File + line citations** — `docs/pipeline-rules.md:77–84`, `pipelines/promote_comparison_section.py:15–28`, `README.md:96–99`, `docs/architecture-current.md:55–69`.

### A5. `output/source-import-health.json` (the consumer contract)

- **Why critical** — written by `verify_import_health.py`, read by `ops/watchdog/pull_watchdog.py` and by the chain's L1 gate (`pipelines/check_reference_freshness.py`'s `check_l1_freshness()` per GAP-015). Schema is normative (`docs/import-health-schema.md`); do not change field names.
- **Cutover risk** — if Phase 2 moves the writer to a Supabase cron, the file path (`output/source-import-health.json`) and schema must stay identical. The file is gitignored today (per `docs/import-health-schema.md:6–8`); an EF that writes to Supabase storage instead would force a consumer-side port.
- **File + line citations** — `docs/import-health-schema.md:1–14`, `pipelines/verify_import_health.py:51–53`, `docs/risk-register.md` GAP-015.

### A6. `dist/modules/player-trace.json` + `dist/modules/source-value-lineage.json` + `dist/modules/live-page-scrape.json` + `dist/modules/comparison-chain-status.json` (monitor outputs)

- **Why critical** — published monitor artifacts. `player-trace` is rebuilt every 6 h by `player-trace-rebuild.yml`; `live-page-scrape` is consumed by `build_source_value_lineage.py` (the builder must NOT re-scrape per `pipelines/build_source_value_lineage.py:40–46`); `comparison-chain-status` is the chain's fail-closed status surface (`rebuild-chain.yml:92–100`).
- **Cutover risk** — each is a derived artifact of a different pipeline. Phase 2 must keep the same writer list (no new monitor artifact) and the same consumer contracts. GAP-031 notes `check_data_accuracy.py` is only as fresh as the last manual run; Phase 2 should not introduce more such artifacts.
- **File + line citations** — `pipelines/build_player_trace.py:1–12`, `pipelines/build_source_value_lineage.py:40–77`, `.github/workflows/player-trace-rebuild.yml:33–39`, `docs/risk-register.md` GAP-031.

---

## B. Jobs that silently stall or continue on stale inputs

These are the workflows that exit 0 (or stay silent) while their data goes stale. Each is flagged SILENT in inventory 01; here we cite the **exact line** that produces the silence.

### B1. ESPN daily pull (`espn-supabase-sync.yml`)

- **The fail-open wrapper** — `pipelines/pull_espn_projections.py` is called with `|| echo "Scraper failed, using existing data"` in `.github/workflows/espn-supabase-sync.yml:41`. The wrapper swallows a failed scrape and the workflow continues.
- **The skip path** — if `/tmp/espn_projections.csv` is missing, the save step writes `"No fresh ESPN data, skipping Supabase save"` and exits 0 (`.github/workflows/espn-supabase-sync.yml:54–56`). The workflow then runs the commit step (line 58–68); with no changes staged, `git diff --cached --quiet` exits 0 and no commit happens. **Result: a multi-day scraper outage leaves the badge green and Supabase row count unchanged.**
- **How a stale input is consumed** — the chain's `verify_import_health.py` reads `data/raw/sources/espn/<date>/snapshot.json` and the `public.espn_season_projections` table; an empty / missing snapshot path returns "MISSING espn" status (per `verify_import_health.py:24` "ESPN projections are a daily live [iff] the content vintage is within 2 days"). **However**, the same `data/raw/` is gitignored and the snapshot manifest is overwritten by any successful pull — so a failed pull leaves the **old** manifest in place and `verify_import_health` says "ok" against stale content. This is a known fail-open path; cited as SILENT in inventory 01 row 2.
- **Why this matters for the cutover** — moving the writer to an EF / cron does not change this behavior; the `|| echo` wrapper is in the workflow file, not the Python. Phase 2 must either remove the wrapper or replace the workflow step's silent path with a hard `exit 1`.
- **File + line citations** — `.github/workflows/espn-supabase-sync.yml:41, 54–56`, `docs/health/claude-best-practices.md` (2026-10-02 entry cites this fail-open).

### B2. Rebuild chain — red publish, no notify

- **The fail-open path** — `rebuild-chain.yml` is on a 6-hourly cron (`'17 */6 * * *'` line 20). On a red chain the workflow publishes only the status (line 92–100), commits it, and fails the job (line 133–137). The status is visible on the monitor.
- **The silent stall** — runs 3 to 9 (all on record) failed; the latest green rebuild was a **local** run (`runner: "local"` per `output/comparison-chain-status.json` per `docs/health/claude-best-practices.md` and `docs/claude-log.md` 2026-10-02). **There is no notify step** — no `actions/github-script` issue action, no Slack webhook, no email on red. A red chain is found by an audit, not by the system.
- **The stale-input risk** — `make sync` copies the (possibly stale) fixture into `dist/modules/`; the deploy gate on `pages.yml` (lines 47–51) blocks only if the last commit touched a file **outside** `dist/modules/`. The chain's "Automated chain status (chain failed; fixture not updated)" commit touches `dist/modules/comparison-chain-status.json` — `dist/modules/` only — so the deploy gate does **not** block a subsequent daily `pages.yml` run. A red chain + a daily Pages run = the live site is one `comparison-chain-status.json` file ahead of the actual chain status.
- **File + line citations** — `.github/workflows/rebuild-chain.yml:17–22, 73–137`, `.github/workflows/pages.yml:42–51`, `docs/health/claude-best-practices.md` (rows P2, P5, B5, item 5), `docs/risk-register.md` GAP-019 / GAP-007.

### B3. CBS ROS pull (`cbsros-supabase-sync.yml`)

- **The fail-open wrapper (mild)** — the workflow's "Scrape CBS ROS projections" step exits non-zero on failure (line 41–42, save step gated `if: steps.scrape.outcome == 'success'` on line 45). If the scraper fails, the save step is skipped and the workflow exits 0 (no explicit `exit 1` after the scrape failure). The badge stays green; the snapshot is missing.
- **The stale-input risk** — `verify_import_health.py` will catch it on the next chain run; the gap is between the weekly CBS ROS pull and the next chain run. **Mild** — the next chain run within 6 h catches it.
- **File + line citations** — `.github/workflows/cbsros-supabase-sync.yml:36–50`.

### B4. FantasyCalc drift + refresh (`fantasycalc-drift.yml`)

- **The silent path on API-down** — `check_fantasycalc_drift.py` exits 2 on API unreachable (line 18) → the script's `SystemExit` propagates → the step exits non-zero → the workflow exits non-zero → badge red. **NOT silent** — this one fails loudly.
- **The silent path on no-drift** — `if python3 pipelines/check_fantasycalc_drift.py --trigger; then` (line 54) — exit 0 → "No drift detected" → nothing committed → exit 0. This is the **intended** silent path; it is silent only when no drift was detected, which is the healthy state. A stale `data/raw/sources/fantasycalc/week-4/snapshot.json` is graded by the watchdog, not by this workflow.
- **The silent path on stale refresh** — the refresh step (line 67–68) writes `public.source_trade_values` rows; if the delete count vs insert count mismatch (`refresh_fantasycalc_supabase.py:7` fail-closed), the script exits 1 → workflow red. Loud, not silent.
- **File + line citations** — `.github/workflows/fantasycalc-drift.yml:47–60`, `pipelines/check_fantasycalc_drift.py:18`, `pipelines/refresh_fantasycalc_supabase.py:1–8`.

### B5. Player-trace rebuild (`player-trace-rebuild.yml`)

- **The silent stale path** — `build_player_trace.py` reads the fixture + every source's snapshot + every source's section + every source's reindexed output. On a red chain, the fixture is the last green one and the trace timestamps are silently stale. No failure — the script just builds against old data. The workflow exits 0.
- **Why this matters** — the trace powers the "Player Trace" monitor section; if a user looks at the trace after a red chain, they see last-green-fixture numbers. The window is short (next chain run ≤6 h), but real.
- **File + line citations** — `.github/workflows/player-trace-rebuild.yml:33–39`, `pipelines/build_player_trace.py:34–67`.

### B6. `output/source-import-health.json` consumer state

- **The silent age risk** — the L1 gate (`check_l1_freshness()` per GAP-015) compares status + vintage only; it does not check the `checked_at` age of the file. A 30-day-old `output/source-import-health.json` can say "ok" and a promote will accept it. Phase 2 design must add an age limit (GAP-015 open) before this gate is cutover-critical.
- **File + line citations** — `docs/risk-register.md` GAP-015, `docs/import-health-schema.md` (no max-age field defined).

### B7. Hourly trigger loop (`source-vintage-check.yml`) — added on review (Roman, 2026-10-03)

- **The single-point-of-failure shape** — the 6-hourly `rebuild-chain.yml` cron is vestigial; the real trigger is this hourly dispatcher. If the vintage-check workflow itself dies (checkout failure, `gh` CLI auth failure on the dispatch step, or the repo's Actions disabled), no rebuild is dispatched and the chain silently degrades to its 6-hourly cron — fresh vintages wait up to 6 h instead of ~1 h, and `code_changed` dispatches (JEG-205) never fire at all. Nothing notifies on this degradation; the chain's own status just shows the older cadence.
- **The fail-closed-toward-work property** — any vintage-check error reports `changed=True` (by design), so a broken checker dispatches a no-op rebuild every hour rather than going silent. The risk is not silence but the inverse: an undetected broken checker burns 24 no-op chain runs a day. The monitor does not distinguish "dispatched because vintage moved" from "dispatched because the checker errored" — both look like a green hourly run.
- **File + line citations** — `.github/workflows/source-vintage-check.yml` (full file, 90 lines); JEG-205/JEG-268 in the in-file comments.

---

## C. Jobs needing manual intervention

These are workflows that cannot produce useful output without a human in the loop.

### C1. Promote (every source, on every review verdict = `hold`)

- **Where** — `pipelines/rebuild_comparison_chain.py:18–28`: "Review verdicts are NEVER modified by this chain. A 'hold' stays a 'hold'… Only genuine 'ready' verdicts are promoted."
- **How often** — at minimum, every time a new week's content differs from the prior week (USA Today, FantasyPros, CBS, FantasyCalc all refresh weekly). On record: GAP-019 says `usatoday` and `fantasypros` returned `hold` on CI run `36868501121` (2026-10-01).
- **What the human does** — `make comparison-review REINDEXED_FILE=output/comparison-reference/...-reindexed.json --triage triage.json`, inspect the review report, then `make comparison-promote REVIEW_FILE=... APPROVE="<name> <YYYY-MM-DD> <reason>"`.
- **Cutover risk** — Phase 2 must not auto-resolve holds. The current chain refuses to auto-resolve (line 18–28); an EF / cron that short-circuits this would be a silent regression.
- **File + line citations** — `pipelines/rebuild_comparison_chain.py:18–28`, `pipelines/promote_comparison_section.py:15–28`, `docs/pipeline-rules.md:53–84`, `docs/risk-register.md` GAP-019.

### C2. Razzball refresh (no repo puller)

- **Where** — `docs/risk-register.md` GAP-024 + GAP-030: "Razzball-through-Supabase code (JEG-18) is built but cannot be merged yet… `pipelines/pull_razzball_ros.py`, named in JEG-18 as the puller, is not in the repo, so the real snapshot row shape is inferred, not verified."
- **How often** — daily (Razzball publishes daily ROS updates; nothing currently runs).
- **What the human does** — pulls Razzball on their machine, runs `python3 pipelines/save_razzball_references.py` to save to `public.razzball_projections`. The `import_supabase_references.py` chain then re-stamps the snapshot.
- **Cutover risk** — until a repo-owned puller lands, Razzball cannot be cut over. Phase 2 must add the puller OR keep Razzball out of the EF/cron flow entirely.
- **File + line citations** — `docs/risk-register.md` GAP-024 / GAP-030.

### C3. CBS article / USA Today article — discovery fallback

- **Where** — `ops/watchdog/pull_cbs.py:55` raises `DiscoveryFailed` when no week-N slug resolves; `ops/watchdog/pull_usatoday.py:67–69` raises `DiscoveryFailed` on truncated sitemaps. **Both fail closed** — the right behavior, but the cron worker then has to inspect.
- **How often** — only when USA Today changes its sitemap structure or CBS renames a slug. Both have happened — USA Today changed the article slug between week 3 and week 4 (`pull_usatoday.py:32–38` note).
- **What the human does** — runs the discovery with `--url <pinned>` to override; OR fixes the discovery regex; OR waits for the next week.
- **Cutover risk** — the same fail-closed contract must hold in EF/cron form; an EF that returns the last-known URL on `DiscoveryFailed` would be a silent regression.
- **File + line citations** — `ops/watchdog/pull_cbs.py:42–54`, `ops/watchdog/pull_usatoday.py:48–69`, `docs/watchdog.md:85–98`.

### C4. Audit-table migration (Phase-2-relevant)

- **Where** — `sql/migrations/001_pipeline_write_audit_repair.sql:3` self-labels `DESIGNED — DO NOT EXECUTE without Jeremy's review`. Every save step that uses `WriterAudit` currently hits `HTTP 400` because `code_revision` and `error_message` columns are missing on the live table.
- **How often** — once, when Jeremy approves it.
- **What the human does** — opens the Supabase SQL editor, runs the migration, runs `NOTIFY pgrst, 'reload schema';`.
- **Cutover risk** — until this migration runs, every GH-side save that uses `WriterAudit` will fail closed at the writer. The audit helper is wired into every save step per `docs/SUPABASE_WRITER_AUDIT.md:113–118`. **Phase 2 cannot move saves to an EF without first fixing the audit table — every EF write would 400 on `start()`.**
- **File + line citations** — `sql/migrations/001_pipeline_write_audit_repair.sql:3, 11–17`, `pipelines/lib/writer_audit.py:65–74`, `docs/SUPABASE_WRITER_AUDIT.md:113–118`.

### C5. Schema-cache reload after DDL

- **Where** — every committed migration ends with `NOTIFY pgrst, 'reload schema';` (e.g. `sql/migrations/002_cbs_ros_projections.sql` ends after the indexes; `004` line 18–20; `005` line 19–20; `006` line 24–25). Until the reload, PostgREST may 404 a new table (the `cbs_ros_projections` precedent per `sql/migrations/003_razzball_projections.sql:6–7`).
- **How often** — every DDL change.
- **What the human does** — runs the NOTIFY manually after the migration.
- **Cutover risk** — an EF / cron that creates tables on the fly would need its own NOTIFY step. Phase 2 design must not assume PostgREST auto-reloads.
- **File + line citations** — `sql/migrations/002_cbs_ros_projections.sql:30–37` (full index DDL), `sql/migrations/003_razzball_projections.sql:6–7`, `sql/migrations/004_source_trade_values_bake_version.sql:18–20`, `sql/migrations/005_source_trade_values_grain_bake_aware.sql:19–20`, `sql/migrations/006_retire_unversioned_upsert_grain.sql:24–25`.

---

## D. State that exists only in GitHub logs (no durable surface)

These are the things the repo records only as GitHub Actions log output or as cron log lines. If those logs are lost, the state is lost.

### D1. Cron run-state from the on-machine watchdog

- **What** — `ops/watchdog/pull_watchdog.py:38` reads the goal-workspace `runs.log` (the "today's run" lines per source). The state of "did the cron actually run today?" lives in that log; no `prompt`, no slack, no issue, no `output/cron-runs.json`.
- **Where to recover it** — the runs.log in `~/workspace/goals/...` (out-of-repo; `docs/watchdog.md:14–16`). If the user deletes the log, "we ran at 09:07" is unrecoverable.
- **Cutover risk** — if Phase 2 moves the watchdog to a Supabase cron, the run-history should land in a Supabase table (e.g. `public.pipeline_run_audit`) so it is durable. Today: it is not.
- **File + line citations** — `ops/watchdog/_common.py` (`todays_run_lines`), `ops/watchdog/pull_watchdog.py:38`, `docs/watchdog.md:32–46`.

### D2. The comparison-chain "runner" field

- **What** — `output/comparison-chain-status.json` records `runner: "local"` (per `docs/claude-log.md` 2026-10-02). The status file is gitignored and runtime-only; the "this green rebuild came from my laptop, not from CI" signal lives nowhere else.
- **Where to recover it** — the status file (gitignored, runtime). Once overwritten by the next chain run, the prior `runner: "local"` label is lost.
- **Cutover risk** — if Phase 2 moves the chain to a Supabase cron, the `runner` field must be set to `supabase-cron` (or similar). The signal — "did production run on the production cron or on someone's laptop?" — must remain in the status file.
- **File + line citations** — `docs/health/claude-best-practices.md` P5, `docs/claude-log.md` 2026-10-02.

### D3. Per-stage stage-1/2/3 wall-clock + step outputs

- **What** — the chain's internal step outputs (match counts, reference counts, reindex verdicts) live in `output/comparison-candidates/`, `output/comparison-reference/`, `output/comparison-review/` (gitignored). The Actions log shows what the script printed; the only durable record is the review report JSON.
- **Where to recover it** — the `output/` tree, gitignored. If the next chain run cleans `output/` (it does not — `output/` is preserved across runs), the prior per-stage output is lost.
- **Cutover risk** — Phase 2 should not change which outputs are durable. The chain's promotion record (the replaced section as a rollback record, per `docs/pipeline-rules.md:83–84`) is the most important to preserve; it lives under `output/comparison-promotions/` and is **not committed**.
- **File + line citations** — `docs/pipeline-rules.md:83–84`, `Makefile:62–82` (`comparison-merge/reindex/review/promote` targets).

### D4. Failure reasons on every source

- **What** — `output/source-import-health.json`'s per-source `failure_reason` field is the only machine-readable failure surface (per `docs/import-health-schema.md:48–66` schema). When a source is `failed`, the reason text is the diagnostic. There is no `last_failure_at`, no `consecutive_failures`, no notification.
- **Where to recover it** — the file itself, gitignored. If the next check is `ok`, the prior failure reason is overwritten.
- **Cutover risk** — Phase 2 must preserve the `failure_reason` shape and ideally add `last_failure_at` + `consecutive_failures` so a cutover alert has enough history to fire.
- **File + line citations** — `docs/import-health-schema.md:48–66`, `docs/risk-register.md` GAP-015.

### D5. The promotion's `APPROVE` string

- **What** — `promote_comparison_section.py:21` records `--approve "<name> <YYYY-MM-DD> <reason>"` on the promotion record under `output/comparison-promotions/`. This is the audit trail for "who promoted what when and why".
- **Where to recover it** — the `output/comparison-promotions/<src>-<date>-promotion.json` file. Gitignored. If the user does not commit or back up these, the trail is local-only.
- **Cutover risk** — Phase 2 must preserve the approve string and ideally surface it on the monitor. The current `make comparison-promote` requires the operator to type the string; an EF that auto-resolves the approval is the silent-regression pattern this audit is flagging.
- **File + line citations** — `pipelines/promote_comparison_section.py:21`, `Makefile:75–82`, `docs/pipeline-rules.md:79–83`.

---

## Summary of risks by cutover-readiness

| Bucket | Item | Severity (for cutover) | Citation |
|---|---|---|---|
| A1 | `source_trade_values` (3 sources) | High — backplane for the chain | `risk-register.md` GAP-019 |
| A2 | `espn/cbs/cbsros/razzball` source tables | High | `risk-register.md` GAP-024/030 |
| A3 | `public.players` identity table | High — outside this repo | `architecture-current.md:108` |
| A4 | `comparison-sources-data.json` live fixture | High — only writer must stay only-writer | `pipeline-rules.md:77–84` |
| A5 | `output/source-import-health.json` consumer contract | High — normative schema | `import-health-schema.md:1–14` |
| A6 | `dist/modules/*` monitor artifacts | Medium | `risk-register.md` GAP-031 |
| B1 | ESPN daily pull fail-open | High — silent stale | `espn-supabase-sync.yml:41, 54–56` |
| B2 | Rebuild-chain red + no notify | High — red on record, silent to ops | `risk-register.md` GAP-019 |
| B3 | CBS ROS weekly pull skip-on-fail | Medium — chain catches within 6 h | `cbsros-supabase-sync.yml:36–50` |
| B4 | FantasyCalc drift path | Low — loud on fail | `fantasycalc-drift.yml:47–60` |
| B5 | Player-trace stale against red chain | Medium — short window | `player-trace-rebuild.yml:33–39` |
| B6 | `source-import-health.json` age gate | Medium — GAP-015 | `risk-register.md` GAP-015 |
| C1 | Promote hold → human | High — chain refuses auto-resolve | `rebuild_comparison_chain.py:18–28` |
| C2 | Razzball refresh | High — no repo puller | `risk-register.md` GAP-030 |
| C3 | CBS / USA Today discovery | Medium — fail-closed is correct; human must inspect | `pull_cbs.py:42–54`, `pull_usatoday.py:48–69` |
| C4 | Audit-table migration | High — every save currently 400s on `WriterAudit.start()` | `001_pipeline_write_audit_repair.sql:3, 11–17` |
| C5 | PostgREST schema reload after DDL | Medium — known precedent | `003_razzball_projections.sql:6–7` |
| D1 | Cron run-state from on-machine watchdog | Medium — lost if `runs.log` is gone | `pull_watchdog.py:38` |
| D2 | `runner` field on chain status | Medium — labels a laptop run as production | `claude-log.md` 2026-10-02 |
| D3 | Per-stage step outputs | Low — preserved across runs in `output/` | `pipeline-rules.md:83–84` |
| D4 | `failure_reason` shape | Medium — no `consecutive_failures` field today | `import-health-schema.md:48–66` |
| D5 | Promotion `APPROVE` string | High — auto-restore would be silent regression | `promote_comparison_section.py:21` |

---

## Items Phase 2 should consider before designing the cutover

1. **The audit-table migration (`001_pipeline_write_audit_repair.sql`) must run first.** Every save currently fails closed at `WriterAudit.start()` because the live table is missing `code_revision` and `error_message` (per the migration's own header). A cutover that moves writes to an EF without first fixing this will 400 on every write.
2. **The 6-hourly chain must gain a notify step** (or `pg_cron` equivalent on the new control plane) before cutover. Today it can fail red and no one knows (GAP-019 + `docs/health/claude-best-practices.md` P2).
3. **The "only writer to the live fixture" rule must be preserved** (`docs/pipeline-rules.md:77–84`). An EF / cron that promotes without `--approve` is the silent-regression pattern.
4. **The `|| echo "Scraper failed, using existing data"` wrapper in `espn-supabase-sync.yml:41`** must be removed or replaced with a hard `exit 1` before cutover; today it is a silent stale path.
5. **Razzball cannot be cut over** until a repo-owned puller lands (GAP-030); either the puller is added or Razzball stays on the manual / on-machine path.
6. **The promote L1 freshness gate must add a `checked_at` age limit** (GAP-015) before cutover; today a 30-day-old `ok` health file still passes the gate.
7. **The deploy gate (`pages.yml:42–51`) needs to be re-examined** for the new control plane. Today a `dist/modules/`-only commit bypasses the product-changed block; a cutover must not carry that hole forward.