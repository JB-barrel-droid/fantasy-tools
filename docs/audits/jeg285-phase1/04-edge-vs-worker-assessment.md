# 04 — Edge Function vs External Python Worker Assessment

**Phase:** JEG-285 Phase 1 (Discovery / current-state inventory)
**Method:** for each in-scope pipeline, walked the runtime characteristics (cold start, network, compute, secret surface, state, run time, idleness) and assigned a Phase-1-safe-or-needs-worker verdict. **No recommendation of which to build first** — that is Jeremy's Phase-2 call. The goal here is to inventory the runtime shape, not to redesign.
**Read:** every workflow + every `pipelines/pull_*.py` + `pipelines/save_*_references.py` + `pipelines/import_supabase_references.py` + `pipelines/verify_import_health.py` + `pipelines/rebuild_comparison_chain.py` + `pipelines/check_fantasycalc_drift.py` + `ops/watchdog/*`. Every claim cites repo path + line.

## Edge Function vs External Python Worker — short-reference labels |

| Label | Used when… |
|---|---|
| **EF-SAFE** | A Supabase Edge Function can run the step end-to-end without breaking the pipeline's fail-closed contract. Implies: low compute, no native sub-process / curl / external binary, runtime fits the Edge function limits (CPU-time, memory, request time), secrets already in the project's secret store, no long-lived process needed. |
| **NEEDS-WORKER** | The step requires a Python interpreter with `pip packages` (Pandas, Requests with retry, etc.), `urllib`-vs-`curl` matters, sub-second + sustained CPU, on-disk filesystem (`/tmp/` CSV caches), or runs >Edge function request limit. Implies a long-lived or scheduled worker outside Supabase. |
| **HYBRID** | Edge Function for the trigger / scheduling / orchestration; worker for the heavy transform. |

The split rule follows from what is in the repo today: every GH-side step today runs `python3 pipelines/X.py` from `ubuntu-latest` with `actions/setup-python@v5` Python 3.12 + `pipelines/gh_sbclient.py` on `PYTHONPATH`. An Edge Function cannot host that stack today without a port to Deno/TS (or a container function — Supabase supports them, but the runtime characteristics differ).

## Per-pipeline / per-step assessment

#### 1. `espn-supabase-sync.yml` — ESPN daily pull + save

- **Pull step (`pipelines/pull_espn_projections.py`)** — `urllib.request` against the ESPN projections API (`pipelines/pull_espn_projections.py:58–60`); CSV + JSON file writes to `/tmp/`; runs as one Python process; compute is JSON parse + CSV write (~5–30 s wall-clock for ~300 rows; verified cadence `daily 06:10 CT` per script line 20). **NEEDS-WORKER** today (Python + file IO; no Edge Function language compatibility).
- **Save step (`pipelines/save_espn_cbs_references.py --source espn`)** — Python, PostgREST `POST` via service-role shim, ~1–3 s wall-clock; idempotent on the upsert grain. **HYBRID possible** if the save is rewritten in TS using `supabase-js` and the CSV is replaced by JSON over the wire. Today: **NEEDS-WORKER** (Python only).
- **Verdict per step** — Pull: NEEDS-WORKER. Save: HYBRID possible (TS port); NEEDS-WORKER today. **Pipeline as a whole**: NEEDS-WORKER today; HYBRID if the save is rewritten in TS and the pull is split.
- **Runtime / compute / secret reason** — ESPN's projections API has no auth header today (the script's `urllib.request` call line 21 carries only a UA), so the secret surface is small. The save step needs service-role bearer key — that maps cleanly into the Edge Function secrets surface. The blocker is the Python runtime requirement for the pull.

#### 2. `cbsros-supabase-sync.yml` — CBS ROS weekly pull + save

- **Pull step (`pipelines/pull_cbs_ros_projections.py`)** — Python, `urllib.request` against 4 CBS pages (QB/RB/WR/TE); HTML parse + JSON snapshot write; ~10–60 s wall-clock for ~700 rows. **NEEDS-WORKER** today.
- **Save step (`pipelines/save_cbsros_references.py`)** — Python, PostgREST upsert via service-role; ~2–5 s. **HYBRID possible** with TS port. Today: NEEDS-WORKER.
- **Verdict** — Same as ESPN. NEEDS-WORKER today; HYBRID possible with TS rewrite.

#### 3. `fantasycalc-drift.yml` — FantasyCalc drift check + refresh

- **Drift check (`pipelines/check_fantasycalc_drift.py`)** — `urllib.request` to one FantasyCalc API URL (`check_fantasycalc_drift.py:31–32`); compares against on-disk snapshot. ~1–3 s wall-clock for 25 sample rows; idempotent. **HYBRID possible** — the API URL is small, the comparison is JSON-deep-equal-able, and a TS port is feasible. Today: NEEDS-WORKER.
- **Refresh (`pipelines/refresh_fantasycalc_supabase.py`)** — Python, `delete + post` against `public.source_trade_values`, 580 → 584 rows. ~5–10 s wall-clock. **HYBRID possible** with TS port.
- **Verdict** — Both steps **HYBRID possible**. Today: NEEDS-WORKER.

#### 4. `rebuild-chain.yml` — 6-hourly vintage-gated full chain

- **The chain runs the whole stage 1→3 sequence** — `import_supabase_references.py --source fantasycalc|usatoday|fantasypros|espn|cbs|cbsros|razzball` (loop, 7 sources), then `verify_import_health.py`, then `rebuild_comparison_chain.py --nfl-week N`. The latter internally subprocesses 7 stages (`make source-match`, `make source-reference`, `make comparison-section`, `make comparison-reindex`, `make comparison-review`, `make comparison-promote`, `make build-adjustment-inputs`, `make build-adjusted-fixture-sections`) — see `pipelines/rebuild_comparison_chain.py:1–60` and the `Makefile:50–82` `comparison-*` targets. Each stage runs Python + JSON in/out, but `make comparison-review` calls `pipelines/review_comparison_candidate.py` which can write 1000+ row JSON files and produce the review report. Total wall-clock per source: ~30–120 s; sequential = 3–10 min. **NEEDS-WORKER** (Python + JSON IO + 6-source loop; Edge Function request limit will be exceeded).
- **Verdict** — NEEDS-WORKER.

#### 5. `pages.yml` — Deploy path

- **What it does** — `make sync` + `make validate` + `build_source_value_lineage.py` + Pages upload. `make sync` copies reference artifacts into `dist/` (`pipelines/sync_dashboard_artifacts.py`); `make validate` runs `naming` + `reference` + `sync` + `guard-harness` + `test-unit` per the `Makefile:179` recipe. Total wall-clock ~30–90 s, mostly test time.
- **EF candidate** — The Pages upload step is `actions/upload-pages-artifact@v3` (line 53–54); that is GitHub-side, not Supabase-side. The deploy step (`actions/deploy-pages@v4` line 56–57) is GitHub-only. **The deploy path stays on GitHub Pages today.** Phase 2 design that moves deploys to a Supabase Edge Function would also have to migrate the host target (away from GitHub Pages), which is out of scope for orchestration cutover.
- **Verdict** — Out-of-scope-for-cutover (different host target — GitHub Pages). For an EF-vs-worker assessment of just the **build** step, NEEDS-WORKER (Python `make validate` + lineage build); the **deploy** itself is GitHub Pages.

#### 6. `player-trace-rebuild.yml` — 6-hourly monitor trace rebuild

- **What it does** — `pipelines/build_player_trace.py` reads the fixture + every source's snapshot + every source's section + every source's reindexed output, builds a trace JSON. Wall-clock ~3–10 s for ~600 players × 6 sources. Python + JSON IO + filesystem glob. **NEEDS-WORKER** (Python only).

#### 7. `preview.yml` — PR preview build

- **What it does** — `make sync`, `make validate` (blocking here), `build_source_value_lineage.py`, manifest build, `npm ci --prefix tests/rendered_gate`, `npx --prefix tests/rendered_gate playwright-core install --with-deps chromium`, `node tests/rendered_gate/gate.mjs dist` (the rendered gate), and a `github-script` PR comment. Wall-clock ~3–6 min (Playwright install dominates). NEEDS-WORKER (Python + Node + Playwright + headless Chromium).

#### 8. `ops/watchdog/pull_watchdog.py` + per-source ingesters — on-machine cron jobs

- **What they do** — `pull_watchdog.py` is the daily 07:05 CT grader; the per-source ingesters (`ingest_usatoday.py`, `ingest_cbs.py`, `refresh_fantasycalc.py`, `pull_usatoday.py`, `pull_cbs.py`) are the discover-pull-save-verify wrappers. Each is Python with `urllib`/`curl`; uses `pipelines/lib` + the goal-workspace skill via `sys.path.insert`. Wall-clock per ingest: 30–180 s. NEEDS-WORKER today.
- **EF candidate** — The watchdog itself is a 9-source grading loop (`pull_watchdog.py` lines 49 + 110 + 121+); an Edge Function could host a TS port that reads the same `output/source-import-health.json` contract and writes back the same shape. The per-source pullers are NEEDS-WORKER (HTML scraping + sitemap discovery).

#### 9. The 6-hourly `verify_import_health.py` call inside `rebuild-chain.yml`

- **What it does** — `python3 pipelines/verify_import_health.py --nfl-week $N`, writes `output/source-import-health.json`. ~5–15 s. **HYBRID possible** — the verification is a JSON read + sha256 compare + a write; the only Python requirement is `lib.publication_windows` for window logic. Today: NEEDS-WORKER.

#### 10. The Saturday puller (out-of-repo, but pipeline-state-relevant)

- **Goal-workspace `~/workspace/goals/football-signal-database-and-app/lottery/bin/build_sources_dashboard.py --refresh-fc`** — pulls all 24 FantasyCalc combos (`refresh_fantasycalc.py:48–49`), writes to `lottery/data/sources_cache/`. NEEDS-WORKER (24 sequential API calls + cache writes; 60–180 s).

## Summary table

| # | Pipeline / step | Today | EF-SAFE? | Reason |
|---|---|---|---|---|
| 1 | ESPN pull | NEEDS-WORKER | No | Python + `/tmp/` CSV writes; no Edge Function language match |
| 1 | ESPN save | NEEDS-WORKER | HYBRID | TS port to `supabase-js` is feasible; service-role key in EF secrets |
| 2 | CBS ROS pull | NEEDS-WORKER | No | Python + HTML parse + 4-page loop |
| 2 | CBS ROS save | NEEDS-WORKER | HYBRID | same as ESPN save |
| 3 | FantasyCalc drift check | NEEDS-WORKER | HYBRID | small JSON compare; TS port is feasible |
| 3 | FantasyCalc refresh | NEEDS-WORKER | HYBRID | PostgREST delete+insert; TS port feasible |
| 4 | Full rebuild chain (7 stages × 6 sources) | NEEDS-WORKER | No | 3–10 min wall-clock + Python + subprocess orchestration; Edge Function request limit exceeded |
| 5 | GitHub Pages deploy | n/a | n/a | GitHub Pages is the deploy target, not Supabase; deploy stays on GitHub |
| 6 | Player trace rebuild | NEEDS-WORKER | No | Python + filesystem glob |
| 7 | PR preview build | NEEDS-WORKER | No | Python + Node + Playwright + headless Chromium |
| 8 | Source-pull watchdog (on-machine cron) | NEEDS-WORKER | HYBRID | TS port that reads/writes the same JSON contract is feasible; the pullers underneath remain NEEDS-WORKER |
| 9 | Import-health verification | NEEDS-WORKER | HYBRID | small JSON read + sha256 + write |
| 10 | Goal-workspace 24-combo FantasyCalc pull | NEEDS-WORKER | No | 24 sequential API calls + cache writes |

## Why most "EF candidate" steps are not EF-SAFE today

1. **Language lock-in.** Every scheduled step today is Python 3.12 with `pipelines/lib/*.py` helpers. The Edge Function runtime is Deno + TS (or Node via container functions). A TS port is non-trivial — `lib/canonical_players.py`, `lib/publication_windows.py`, `lib/writer_audit.py`, `lib/scoring.py`, `lib/dataset_status.py`, `lib/nicknames.py`, `lib/preseason_ecr.py` are all Python.
2. **Secret surface today** — every GH-side workflow uses `secrets.SUPABASE_URL` + `secrets.SUPABASE_SERVICE_KEY` only (`rebuild-chain.yml:55–56`, etc.). The Edge Function secrets surface would carry the same two secrets + any new ones (e.g. ESPN API keys if they appear later). That maps cleanly — no secret blocker.
3. **Compute envelope** — Edge Functions cold-start + per-request CPU budget (sub-second to ~30 s) fits individual pullers but not the full rebuild chain. The chain is the canonical example of why a worker still has a place: the 3–10 min wall-clock + the inter-stage subprocess pattern does not fit Edge Function limits without a model change.
5. **State at runtime** — `data/raw/sources/<src>/<vintage>/snapshot.json` is on the GH runner's disk; an EF would either need to read it from Supabase (forcing a snapshot+manifest schema change) or fetch from the source every time (costly + fragile). Both paths imply a redesign.

## What the Edge Function surface would gain if Phase 2 chooses EF for some pieces

- **EF + worker split** — small triggers (drift check, health verification, single-source save) on EF; heavy stages (rebuild chain, Playwright preview, on-machine 24-combo pull) on worker. Phase 2 design choice.
- **EF + cron (`pg_cron`)** — if EF hosts the trigger, Supabase's `pg_cron` becomes the cron surface. The repo today uses GitHub `cron:` syntax only; **no `pg_cron` invocation has been seen in this repo** (verified by grep). Phase 2 must verify whether `pg_cron` is already used on the project (per `docs/architecture-current.md:120` it is unverified).
- **EF secrets vs GH secrets** — EF secrets live in the Supabase project, not in repo `Settings > Secrets`. The mapping is 1:1 for the two secrets above; anything new needs to be added twice (EF + GH) during a transition.

## Inventory-only scope reminder

Per the brief: "No recommendation of which to build first — inventory only." This file's verdicts are about **runtime fit**, not about build order or migration strategy. Phase 2 design makes the sequencing call after Jeremy reviews Phase 1.