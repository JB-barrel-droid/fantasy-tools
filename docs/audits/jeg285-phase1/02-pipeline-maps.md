# 02 — Pipeline Maps (raw source → dashboard/product)

**Phase:** JEG-285 Phase 1 (Discovery / current-state inventory)
**Method:** read each `pipelines/pull_*.py`, `pipelines/save_*_references.py`, `pipelines/import_supabase_references.py`, `pipelines/verify_import_health.py`, `pipelines/rebuild_comparison_chain.py`, plus the relevant workflow files; cross-checked against `docs/supabase-source-mapping.md`, `docs/modular-pipeline.md`, and `docs/architecture-current.md`. Every claim cites repo path + line.
**Scope:** the **trade-value chart** pipeline only. The `weekly_vegas/` and `waiver_wire/` subtrees have their own data flow and are referenced only as siblings; their internals are Phase-2 territory.

The dashboard's pipeline is the four-stage flow from `docs/modular-pipeline.md:11–13`:

```text
source data → reference compute → dashboard build → frontend/site
```

This file walks each in-scope pipeline through that shape, naming the files and tables at every hop and the **expected data vintage** at each hop (per `docs/pipeline-rules.md:95–110`: "Freshness is content vintage, never pull time").

---

## Pipeline A — FantasyCalc (weekly snapshot, drift-gated daily refresh)

```
RAW SOURCE                                  PULL                              TRANSFORM                                       DERIVED                                      DASHBOARD/PRODUCT
live fantasycalc.com API      ──►  ops/watchdog/refresh_fantasycalc.py  ──►  source_trade_values rows          ──►  data/raw/sources/fantasycalc/<vintage>/snapshot.json  ──►  data/fixtures/current/comparison-sources-data.json
(FantasyCalc redraft values  │     (Sunday full 24-combo pull, lines       (8/10/14 team × std/half/full ×           +  public.source_trade_values                          (fantasycalc section, via
 per player per combo)       │      41–82 of refresh_fantasycalc.py)        qb1/qb2; bake_id = fcwk<wk>_            (fantasycalc, as_published)                             rebuild_comparison_chain stage 3)
                             │                                                  <date>_v1; per docs/pipeline-rules.md:135–  (FantasyCalc update is weekly; content vintage = week)
                             │                                                  155 for week-versioning baking)
                             ▼
                    ops/watchdog/pull_watchdog.py (cron 07:05 CT) reads the snapshot meta (week + per-combo cache count) and grades "ok/unchanged/stale/failed" — `docs/watchdog.md:31–46`
```

**Pull cadence** — `refresh_fantasycalc.py` (Sundays, weekly chain) + `pipelines/check_fantasycalc_drift.py --trigger` (daily at 11:45 UTC via `.github/workflows/fantasycalc-drift.yml:18`). The drift check uses the representative combo `ppr=0.5, numQbs=1, numTeams=12` (`check_fantasycalc_drift.py:31–32`).

**Expected data vintage at each hop**
- raw source: FantasyCalc publishes by NFL week (week-designated). Source-content vintage = `week` (the snapshot has no `source_content_date`, NULL per `docs/supabase-source-mapping.md:106–121`).
- pull artifact (`data/raw/sources/fantasycalc/<week>/snapshot.json`): vintage = `week`; manifest records `week` + `bake_id` + `pulled_at`.
- `public.source_trade_values` row: vintage = `week` (column `week`); `source_content_date = NULL` is honest for FantasyCalc (`docs/supabase-source-mapping.md:166–167`).
- Fixture section (`comparison-sources-data.json` → `sources.fantasycalc.combos`): vintage carried via `fetched_at` and the section's source provenance (`docs/pipeline-rules.md:109–110`).
- Monitor: `output/source-import-health.json` writes `vintage_kind: "week_designated"`, `status: "ok"` when `week` matches `nfl_week` (`docs/import-health-schema.md` + `pipelines/verify_import_health.py:9–14`).

**Where pipeline state lives**
- Source raw: `data/raw/sources/fantasycalc/week-N/snapshot.json` (gitignored, `data/raw/` is in `.gitignore`).
- DB: `public.source_trade_values` (`source='fantasycalc'`, `variant='as_published'`), with `week` as vintage column and `bake_id` for week-versioning (`sql/migrations/004_source_trade_values_bake_version.sql:22–24`).
- Fixture: `data/fixtures/current/comparison-sources-data.json` (committed).
- Health: `output/source-import-health.json` (gitignored, runtime state).
- Cron evidence: legacy goal-workspace `data/fixtures`/`runs.log` per `docs/watchdog.md:32–36` (out-of-repo).

---

## Pipeline B — USA Today (weekly chart article)

```
RAW SOURCE                                  PULL                                          TRANSFORM                                      DERIVED                                       DASHBOARD/PRODUCT
USA Today article page        │  ops/watchdog/pull_usatoday.py         ──►   ops/watchdog/ingest_usatoday.py         ──►  data/raw/sources/usatoday/<vintage>/          ──►  data/fixtures/current/
(slug pattern                │  (sitemap discovery via                 (pre-write guard + bake_id stamp:                 snapshot.json                                 comparison-sources-data.json
 "trade-value-chart-week-N-   │   usatoday.com web-sitemap,             "usatwk<wk>_<exec-date>_v<seq>";                 + public.source_trade_values                    (usatoday section, via
 ros-rankings";               │   docs/watchdog.md:85–98)               line 67 of ingest_usatoday.py)                   (usatoday, as_published)                          rebuild_comparison_chain)
 opaque article ID)           │
                              │  ops/watchdog/ingest_cbs.py / ingest_usatoday.py then call save_usatoday_references.build_usatoday_rows_final()
                              │  to apply reindex anchoring at write time (line 41–44 of ingest_usatoday.py)
```

**Pull cadence** — Weekly (Wednesday-anchored: the article publishes Tue → the cron wrapper is the Wednesday ingestion; weekly chain handles Wednesday rebuild). **No dedicated GH workflow** pulls USA Today today; the pull path lives in `ops/watchdog/` and is invoked from the on-machine scheduler. (`weekly_vegas/cron/daily-refresh.md` is for the **Weekly Vegas** pipeline, not USA Today.)

**GH workflow automation** — `pipelines/save_usatoday_references.py` is the writer; `import_supabase_references.py` reads from Supabase. There is **no** `.github/workflows/usatoday-supabase-sync.yml` like there is for ESPN/CBS-ROS — the GH-side path is the shared 6-hourly `rebuild-chain.yml` (line 60–62), which imports USA Today from Supabase.

**Expected data vintage** — week-designated (`docs/import-health-schema.md` + `verify_import_health.py:59` lists `("fantasycalc", "usatoday", "fantasypros", "cbs", "cbsros")` as week-designated). `source_content_date` is populated for USA Today (sample row 2026-09-15 in `docs/supabase-source-mapping.md:108`).

**Where pipeline state lives** — DB (`public.source_trade_values` row + manifest `source_content_date`), repo fixture, `data/raw/sources/usatoday/<vintage>/` (gitignored). Old pinned URL behavior was removed; discovery reads USA Today's own sitemap monthly and grep-matches the chart slug (`docs/watchdog.md:85–98`, `pull_usatoday.py:39–69`).

---

## Pipeline C — FantasyPros (weekly trade-chart article, **not** ECR)

```
RAW SOURCE                                  PULL                                          TRANSFORM                                      DERIVED                                       DASHBOARD/PRODUCT
fantasypros.com article      │  ops/watchdog/pull_fantasypros_chart.py ──►  ops/watchdog/ingest_fantasypros.py        ──►  data/raw/sources/fantasypros/<vintage>/       ──►  data/fixtures/current/
"Week N trade value chart"   │  (candidate_urls pattern,                (same shape as ingest_usatoday:                  snapshot.json                                  comparison-sources-data.json
HTML tables; manually        │   referenced in pull_usatoday.py:11–12)   pre-write guard + bake_id "fpwk<wk>_<date>_v1") (read from public.source_trade_values,             (fantasypros section, via rebuild_
refreshed in the goal-       │                                                                            source='fantasypros', variant='as_published')     comparison_chain)
workspace path is OUT OF       │
SCOPE for Phase 1;          │
fp_trade_chart.csv in goal/  │
files/ is the cached source) │
```

**Important note** — FantasyPros runs **two** flows: the weekly trade chart (this pipeline) and the daily ECR snapshot (`scheduled-pipeline` mentioned in `docs/watchdog.md:32–33` as "FP season snapshot, ESPN, Razzball, ECR weekly, FP trade chart, FantasyCalc, USA Today, CBS"). The ECR flow is **hard-excluded** from the trade-value import (`pipelines/import_supabase_references.py:97` `HARD_EXCLUSIONS = ("ecr", "vegas", "prediction_markets", "prediction-markets")` + backstop at lines 112–114). The repo pipeline reads FP trade values only.

**GH workflow automation** — same as USA Today: no dedicated GH workflow. The `rebuild-chain.yml` 6-hourly job imports FP from Supabase alongside USA Today.

**Expected data vintage** — week-designated; `source_content_date` populated (sample 2026-09-15 per `docs/supabase-source-mapping.md:110`).

**Where pipeline state lives** — DB + fixture + `data/raw/sources/fantasypros/<vintage>/` (gitignored).

---

## Pipeline D — ESPN projections (daily live, file-cache, then DB)

```
RAW SOURCE                                  PULL                                  TRANSFORM                              DERIVED                                         DASHBOARD/PRODUCT
ESPN projections API         │  pipelines/pull_espn_projections.py     ──►  pipelines/save_espn_cbs_references.py   ──►  public.espn_season_projections          ──►  data/fixtures/current/
(Mike Clay model;            │  (.github/workflows/espn-supabase-       (writes public.espn_season_projections     (espn_season_projections rows,                 comparison-sources-data.json
 per-player ROS stats;       │   sync.yml cron: 30 11 * * *)            + player_key via canonical ALIASES,          vintage = espn_snapshot_date)                  (espn section via rebuild_comparison_chain;
 NO timestamp exposed, so    │  Outputs to /tmp/espn_projections.csv     documented in save_espn_cbs_references                                          espn leg is DDF-direct, no reindex
 the script hashes the       │  + /tmp/espn_meta.json (line 41)          lines 5–80)                                                                            to ESPN anchor per rebuild_chain.py:13–16
 normalized payload;                                                                    │
 unchanged -> no write)     │
```

**Pull cadence** — Daily at 11:30 UTC (06:30 CT) per `.github/workflows/espn-supabase-sync.yml:13`. Script itself: "CADENCE: daily 06:10 CT, CONDITIONAL" per `pull_espn_projections.py:20` — the GH cron is the daily invocation point.

**Expected data vintage** — daily (`verify_import_health.py:24`: "ESPN projections are a daily live [iff] the content vintage is within 2 days of the check date"). The CSV carries `espn_snapshot_date` (column, per `docs/supabase-source-mapping.md:142–146`).

**Where pipeline state lives** — DB (`public.espn_season_projections`, created from migration 001's DDL pattern), `data/raw/...` CSV file cache (gitignored), `dist/modules/source-import-health.json` for health.

**Special note** — `pull_espn_projections.py:41` wraps the scraper in `|| echo "Scraper failed, using existing data"`. This is deliberate fail-open at the **workflow layer** (the inner scraper still fails closed). The save step then writes nothing ("No fresh ESPN data, skipping Supabase save" per the workflow line 55). Result: **a multi-day scraper outage is silent** — the badge stays green and Supabase row count stays at whatever it was yesterday. Flagged SILENT in inventory 01.

---

## Pipeline E — CBS trade values (weekly Dave Richards article)

```
RAW SOURCE                                  PULL                                          TRANSFORM                                      DERIVED                                       DASHBOARD/PRODUCT
CBS Sports Dave Richards     │  ops/watchdog/pull_cbs.py              ──►   ops/watchdog/ingest_cbs.py              ──►  data/raw/sources/cbs/<vintage>/            ──►  data/fixtures/current/
weekly trade chart           │  (week-N slug discovery,                 (same shape as ingest_usatoday:                  snapshot.json                                 comparison-sources-data.json
(TableBuilder markup;         │   pull_cbs.py:24–55)                      pre-write guard; QB reuse pattern              + public.cbs_trade_values                      (cbs section, via rebuild_comparison_chain)
 QB published once with       │                                              recorded in save_espn_cbs_references.py       (cbs, as_published)
 "1QB-4 / 1QB-6 / 2QB",       │                                              lines 34–53: one row per scoring for QBs
 reused for every scoring)    │                                              (IMPLIED, never invented)                                                       
```

**Pull cadence** — Weekly. The CBS chain (like USA Today/FP) is invoked from the on-machine scheduler and the goal-workspace `build_sources_dashboard.py`. **No dedicated GH workflow** pulls CBS today; the 6-hourly `rebuild-chain.yml` imports from Supabase.

**QB scoring convention** — CBS publishes ONE QB column ("1QB-4"); the savers write one row per QB per scoring (standard / half_ppr / ppr) with the same 1QB-4 value, documented as IMPLIED. This mirrors the live fixture's own CBS convention (`save_espn_cbs_references.py:34–53`).

**Expected data vintage** — week-designated (`verify_import_health.py:59`).

**Where pipeline state lives** — DB (`public.cbs_trade_values`) + fixture + `data/raw/sources/cbs/<vintage>/` (gitignored).

---

## Pipeline F — CBS Rest-of-Season projections (cbsros)

```
RAW SOURCE                                  PULL                                  TRANSFORM                                          DERIVED                                       DASHBOARD/PRODUCT
cbssports.com ROS            │  pipelines/pull_cbs_ros_projections.py  ──►  pipelines/save_cbsros_references.py     ──►  data/raw/sources/cbsros/<date>/              ──►  data/fixtures/current/
projections pages             │  (.github/workflows/cbsros-supabase-    (writes public.cbs_ros_projections                snapshot.json                                 comparison-sources-data.json
(per position; nonppr slug;   │   sync.yml cron: 0 11 * * 3)             via upsert on (player_key, cbs_snapshot_date);     + public.cbs_ros_projections                   (cbsros section via rebuild_comparison_chain
score derivations computed    │  Outputs /tmp/cbsros_snapshot/           ALIASES for identity                              (cbsros)                                       stages: snapshot → DDF leg (12 legs) → 
locally; fpts column          │  snapshot.json (lines 30–42)             (save_cbsros_references.py:11–18,                                                    section → review/verify, not the generic
preserved)                   │                                              sql/migrations/002_cbs_ros_projections.sql)                                              match/reindex path)
```

**Pull cadence** — Weekly Wednesday 11:00 UTC (06:00 CT) per `.github/workflows/cbsros-supabase-sync.yml:14`.

**Special path** — cbsros does NOT use the generic `match → reference → section → reindex → review → promote` chain because its values are DDF-direct (no reindex). Its chain (per `rebuild_comparison_chain.py:11–16`) is `snapshot → DDF leg (12 legs) → section → review/verify`, with `reindex_status: "complete"` on the section.

**Expected data vintage** — week-designated; column `cbs_snapshot_date` is the upsert key.

**Where pipeline state lives** — DB (`public.cbs_ros_projections`, created `2026-10-01` via the browser SQL editor per `import_supabase_references.py:13`) + fixture + `data/raw/sources/cbsros/<date>/snapshot.json` (gitignored).

---

## Pipeline G — Razzball (weekly, file-cache only as of Phase 1)

```
RAW SOURCE                                  PULL                                  TRANSFORM                                          DERIVED                                       DASHBOARD/PRODUCT
razzball.com ROS             │  NO REPO-OWNED PULLER —                  ──►  pipelines/save_razzball_references.py    ──►  data/raw/sources/razzball/<date>/           ──►  data/fixtures/current/
projections                  │  snapshot is pulled by hand on           (writes public.razzball_projections;             snapshot.json                                 comparison-sources-data.json
                             │  the owner's machine                     │  jakis-style row; gap-fill on first real        + public.razzball_projections                  (razzball section via rebuild_comparison_
                             │  ("pull_razzball_ros.py" mentioned       │  write -- the table was empty before             (razzball, 692 rows as of 2026-10-02            comparison_chain)
                             │  in JEG-18 but is NOT in the repo,       │  per GAP-030)                                   per GAP-030 update; bake-aware grain)
                             │  per risk-register GAP-030)
```

**Pull cadence** — Manual / on-machine. Razzball is **hard-excluded from automated freshness controls** per `docs/risk-register.md` GAP-024 (the fixture says `vintage: 2026-10-01`, correct as of this audit, but nothing will notice when it ages).

**Where pipeline state lives** — DB (`public.razzball_projections`, created `2026-10-02`, empty until the first real save per GAP-030; migration `003_razzball_projections.sql` is in the repo but `NOT YET RUN` per its own line 5 — running is Jeremy's decision). `data/raw/sources/razzball/<date>/snapshot.json` is gitignored and only present on the owner's laptop.

---

## Cross-pipeline: the 6-hourly rebuild chain (`rebuild-chain.yml`)

This is the central stage-2 → stage-3 transform; it is the only writer to the live fixture `data/fixtures/current/comparison-sources-data.json`. Per `rebuild_comparison_chain.py:1–60`:

```text
for each source in [usatoday, fantasycalc, fantasypros, espn, cbs, cbsros]:
   snapshot       ←  data/raw/sources/<source>/<vintage>/snapshot.json   (gitignored)
       ↓
   match          ←  pipelines/match_source_snapshot.py
       ↓
   reference      ←  pipelines/build_source_reference.py
       ↓
   section        ←  pipelines/build_comparison_source_section.py
       ↓
   reindex        ←  pipelines/reindex_comparison_section.py             (skipped for cbsros; its DDF leg is the canonical)
       ↓
   review         ←  pipelines/review_comparison_candidate.py            (writes output/comparison-review/<src>-review.json)
       ↓
   promote        ←  pipelines/promote_comparison_section.py            (gated on review verdict "ready" + APPROVE; the only writer to the fixture)
then, only if every source succeeded:
   fit            ←  pipelines/build_adjustment_inputs.py               (writes data/adjustment-inputs/<src>.json)
   adjusted       ←  pipelines/build_adjusted_fixture_sections.py       (writes candidate under output/, never data/)
```

**Chain fail-closed guards** (`rebuild_comparison_chain.py:18–27`): review verdicts are never modified; only `ready` verdicts promote; a hold/failure halts the chain for that source; partial/zero promotion = failure, not partial success. Chain status is written through a `finally` block so partial/interrupted runs are recorded.

**Where state lives**
- `output/comparison-candidates/<src>/<date>/<src>-<combo>-section.json`
- `output/comparison-reference/<src>-*-reindexed.json`
- `output/comparison-review/<src>-review.json` (the review report; can be `ready` or `hold`)
- `output/comparison-chain-status.json`
- `data/fixtures/current/comparison-sources-data.json` (the live fixture, **only** written by `promote_comparison_section.py`; per `docs/pipeline-rules.md:77–84`)

---

## Cross-pipeline: the deploy path (`pages.yml`)

```
git push (or schedule) on main  ──►  make sync   ──►  make validate  ──►  pages.yml uploads artifact  ──►  GitHub Pages
                                                                       (pipeline-only flags; never                                              (live site
                                                                        data)                                                                https://muse.ai/s/trade-value-chart-xgxi6fxa8xexp2nq
```

**Expected data vintage at deploy** — `comparison.built_at` on the live fixture is the enforced key per `docs/import-health-schema.md` + `make freshness-check MAX_STALE_DAYS=2` per `README.md:96–99`.

**Where deploy state lives** — `dist/` (committed by the GitHub-Actions bot on rebuild-chain runs; deploys via the `pages.yml` upload step). `output/source-import-health.json` (runtime), `output/reference-build-report.json` (validation).

---

## Cross-pipeline: the hourly trigger loop (`source-vintage-check.yml` → `rebuild-chain.yml`)

Added on review (Roman, 2026-10-03) — the 6-hourly chain's schedule is vestigial; the real trigger is this hourly dispatcher:

```text
hourly cron ──► check_source_vintage.py --json ──┬── changed=True (vintage moved or ANY error, fail-closed)
                                                 │         └── gh workflow run rebuild-chain.yml
                                                 └── code_changed=True (pipelines/ code hash moved, JEG-205)
                                                           └── gh workflow run rebuild-chain.yml
                                                        then commit .github/source-vintage-state.json (loop guard)
```

**Design properties for the cutover:** the trigger decision is fail-closed toward extra work (errors dispatch, never silence); exactly-once-per-change is enforced by the committed state file (a failed dispatch does not record the hash, so the next hourly run retries); the `|| true` wrapper (JEG-268) exists because the script's fail-closed exit-1 would otherwise kill the step before dispatch. Phase 2's Supabase-first design must reproduce: (a) the dual data+code trigger, (b) the exactly-once loop guard, (c) error-means-dispatch semantics. Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, automatic `GITHUB_TOKEN`.

## Cross-pipeline: the rendered-output verification loop (`live-page-synthetic.yml`)

Added on review (Roman, 2026-10-03) — the only scheduled check that verifies the *served* product rather than the pipes:

```text
daily 06:00 UTC ──► compute expected build tag from HEAD commit time (JEG-263: never grep the committed dist/index.html)
                    ──► tests/rendered_gate/live.mjs vs https://jb-barrel-droid.github.io/fantasy-tools/
                        (accepts HEAD and HEAD~1 tags; deploy race window)
                    ──► --self-test (the gate must be able to fail)
                    ──► monitor-bridge job: validate JSON, stamp run_url/run_id,
                        judge freshness on a 36h window, upload monitor artifact
```

No secrets (`contents: read` only). STALL with no notify on failure — the monitor's 36h freshness check is the only backstop. Per the standing rule, the monitor's checks must run end to end — live publisher values against rendered numbers — and this gate is the rendered-output half of that. Phase 2 must keep a rendered-output gate; a Supabase-first control plane that only watches pipes would regress this.

---

## Summarized "where does each pipeline's state live" map

| Pipeline | Raw source | Pull step | Saved at (DB) | Snapshot manifest | Health check | Review | Fixture | Monitor |
|---|---|---|---|---|---|---|---|---|
| FantasyCalc | fantasycalc.com | `ops/watchdog/refresh_fantasycalc.py` (Sun weekly) + `pipelines/check_fantasycalc_drift.py` (daily GH cron) | `public.source_trade_values` (as_published, bake-aware) | `data/raw/sources/fantasycalc/week-N/snapshot.json` (gitignored) | `verify_import_health.py` | `output/comparison-review/fantasycalc-*` | `data/fixtures/current/comparison-sources-data.json` (via promote) | `dist/modules/player-trace.json` + `output/source-import-health.json` |
| USA Today | usatoday.com article | `ops/watchdog/pull_usatoday.py` + `ingest_usatoday.py` (on-machine scheduler) | `public.source_trade_values` (as_published) | `data/raw/sources/usatoday/<vintage>/snapshot.json` (gitignored) | `verify_import_health.py` | `output/comparison-review/usatoday-*` | fixture (via promote) | same |
| FantasyPros | fantasypros.com article | `pull_fantasypros_chart.py` + `ingest_fantasypros.py` (on-machine) | `public.source_trade_values` (as_published, ECR-excluded) | `data/raw/sources/fantasypros/<vintage>/snapshot.json` (gitignored) | `verify_import_health.py` | `output/comparison-review/fantasypros-*` | fixture (via promote) | same |
| ESPN | ESPN projections API | `.github/workflows/espn-supabase-sync.yml` (daily 11:30 UTC) → `pull_espn_projections.py` + `save_espn_cbs_references.py` | `public.espn_season_projections` | `data/raw/sources/espn/<date>/snapshot.json` (gitignored) | `verify_import_health.py` | `output/comparison-review/espn-*` | fixture (via promote) | same |
| CBS trade | cbssports.com article | `ops/watchdog/pull_cbs.py` + `ingest_cbs.py` (on-machine) | `public.cbs_trade_values` | `data/raw/sources/cbs/<vintage>/snapshot.json` (gitignored) | `verify_import_health.py` | `output/comparison-review/cbs-*` | fixture (via promote) | same |
| CBS ROS | cbssports.com ROS | `.github/workflows/cbsros-supabase-sync.yml` (Wed 11:00 UTC) → `pull_cbs_ros_projections.py` + `save_cbsros_references.py` | `public.cbs_ros_projections` | `data/raw/sources/cbsros/<date>/snapshot.json` (gitignored) | `verify_import_health.py` | cbsros-specific review (per `rebuild_comparison_chain.py:11–16`) | fixture (via cbsros-specific DDF leg → section path) | same |
| Razzball | razzball.com ROS | manual / on-machine (JEG-18 / GAP-030) | `public.razzball_projections` (table empty; first real save pending) | `data/raw/sources/razzball/<date>/snapshot.json` (gitignored, on owner's machine only) | EXCLUDED per GAP-024 | razzball set | fixture (via promote) | same |

---

## What this file does NOT cover

- The full goal-workspace pipeline (`~/workspace/goals/football-signal-database-and-app/lottery/bin/build_sources_dashboard.py`, `football-signal/bin/` etc.). The repo's import layer reads the *outputs* of those scripts (`docs/supabase-source-mapping.md:14–21`) but does not own them. Phase 2 design will need to enumerate them, but that is read-only inventory work that crosses machine boundaries.
- Player-news (`pipelines/ingest_player_news.py`), vorp-translation (`pipelines/translate_via_vorp.py` + `supabase/migrations/jeg62_vorp_translation.sql`; note the JEG-70 weekly refresh workflow `.github/workflows/vorp-translation-refresh.yml` exists in the working tree but is uncommitted as of `origin/main` `82496aa` — see file 01), waiver_wire, weekly_vegas. These are adjacent pipelines; the brief asks for **scheduled GitHub Actions** orchestration, so they get one-line references here and a Phase-2-by-default deeper dive.
- The on-machine cron schedule itself: this audit lists the **manifest** entries (e.g. `weekly_vegas/cron/daily-refresh.md` line 3) but does not see the actual crontab. Phase 2 design must verify the cron schedules are still what the doc claims (the user noted in CLAUDE.md that the on-machine cron is "outside this repo" and "read only if it informs pipeline state").