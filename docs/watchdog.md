# Source-pull watchdog

**What it is:** the automated fail-checking layer over every pull that feeds
the trade-value chart. Runs after each pull's expected time, distinguishes
"the source didn't change" from "the pull failed", and escalates only what a
worker can't fix.

**Health surface:** `ops/watchdog/health.json` (written by the watchdog;
runtime state, not committed). One JSON object, one source of truth for
both dashboard display and release blocking.

**Scope rule (Jeremy 2026-09-22):** the goal-workspace pull scripts
(`~/workspace/goals/football-signal-database-and-app/lottery/bin/`,
`football-signal/bin/`) keep running untouched until the repo pipeline
replaces them. This watchdog only *reads* their outputs (by absolute path,
same machine) — it never modifies them. New pull logic lives here in
`ops/watchdog/`; old scripts are replaced, not patched in place.

## Components

| File | Role |
|---|---|
| `ops/watchdog/pull_watchdog.py` | The checker. Reads pull outputs + the import-health contract, writes `health.json`, exits 1 on failed/stale. |
| `ops/watchdog/_common.py` | Shared: CT clock, NFL-week calendar, curl fetch, runs-log classification. |
| `ops/watchdog/pull_usatoday.py` | NEW USA Today pull with sitemap-based auto-discovery (replaces the hardcoded article URL). Dry-run by default; `--write` saves a provisional repo-local pull. |
| `ops/watchdog/pull_cbs.py` | NEW CBS pull with week-slug auto-discovery + TableBuilder validation. Dry-run by default; `--write` saves a provisional repo-local pull. |
| `tests/test_pull_watchdog.py` | 34 negative tests (see below). |
| `output/source-import-health.json` | Stage-1 contract (`trade-value-import-health-v1`) consumed for the "landed in Supabase" check. The watchdog refreshes it via `make import-health NFL_WEEK=<n>` before reading. |

## Per-source checks

For each of the 9 pulls (prediction markets, FP season snapshot, ESPN,
Razzball, ECR weekly, FP trade chart, FantasyCalc, USA Today, CBS):

1. **Ran on schedule** — today's runs-log line for the scripted pulls;
   artifact mtime for the browser/weekly ones.
2. **Content vintage, not pull time** — from the pull's own meta
   (vintage/hash, article week). A hash-conditional no-op ("source
   unchanged") is healthy; a missing run is stale.
3. **Sane row counts** — per-source minimums; zero rows fail closed.
4. **Clean identity resolution** — no FAILED/Traceback markers in today's
   log lines; meta n_priced > 0.
5. **Supabase landed** — the `trade-value-import-health-v1` contract
   (see `docs/import-health-schema.md`); `ok` and `stale` both count as
   landed (staleness is about the source's vintage, not the import).

**Fail-closed audit:** a FAILED run must never rewrite its artifact. When
today's log shows FAILED, the artifact mtime must be older than the failed
run — otherwise the failure poisoned downstream and the watchdog flags it
CRITICAL.

**Wednesday rule:** on Wednesdays the FantasyCalc snapshot must be ≤2 days
old (Wednesday cadence); other days ≤7 days. The check reads the weekly
`fantasycalc_snapshot.json` manifest (week label + combo list) and the
representative `fantasycalc_half_12_qb1.json` per-combo cache file — never
the bare `fantasycalc_half_12.json`, which has been a dead legacy file since
the 2026-09-16 per-combo cache split (checking it false-alarmed STALE on
2026-09-22). Zero rows or any missing combo fails closed.

**NFL week convention:** the watchdog passes the pull scripts'
Thursday-flip `nfl_week()` to `make import-health`. Passing a week whose
articles don't exist yet would false-alarm STALE_VINTAGE on every source
(verified 2026-09-22: week-3 CBS slug 404s, no week-3 in the USA Today
sitemap). Known open question: stage 1's first import-health run used week
3 per the board-week (Tue–Mon) convention; the watchdog deliberately uses
the pull-script convention. Revisit if the project standardizes on one.

## Failure path (standing authorization: pull scripts + source discovery only)

When a check fails, the worker:

1. Inspects the runs log + HTTP response.
2. Checks whether the article URL or page schema changed.
3. Runs the repo discovery modules (`pull_usatoday.py` / `pull_cbs.py`
   dry-run) to find the current source.
4. Repairs only the relevant pull/discovery code, re-runs, and verifies
   the Supabase landing + downstream safety.
5. Escalates to Jeremy only if genuinely unfixable, with: what broke,
   what was tried, and what is needed from him.

Green runs are silent. Nothing is published without Jeremy's word.

## USA Today auto-discovery

Article IDs are opaque, so the URL can't be guessed. Discovery reads USA
Today's own monthly web sitemap (`robots.txt` → `web-sitemap-index.xml` →
`web-sitemap-YYYY-MM.xml` on gannett-cdn.com) and greps for the week's
chart slug, newest week first, current + previous month. Raises
`DiscoveryFailed` (fail closed) when nothing is found — never silently
reuses a stale pinned URL. `--url` allows an explicit manual override.

## CBS auto-discovery

Dave Richard's weekly slug embeds the week number; discovery tries the
week-N slugs newest-first and validates the `TableBuilder` markup on each
(the same markup the parser requires). Fails closed when none resolve.

## Negative tests

`tests/test_pull_watchdog.py` — hermetic (tmp dirs, mocked fetch), no
network. Each test simulates the historical miss its check must catch:

- failed pull detected; unchanged-source not misread as failed;
- failed-then-recovered same day reads ok; poisoned artifact flagged
  CRITICAL; intact artifact after failure reads fail-closed;
- stale weekly article; missing cache; thin tables; zero rows; zero priced;
- Wednesday FantasyCalc rule (5-day-old snapshot stale on Wednesday, ok
  on Tuesday);
- FantasyCalc dead-legacy-file guard: fresh-but-dead `fantasycalc_half_12.json`
  does not mask missing real artifacts; stale legacy file does not stale a
  fresh snapshot; zero rows / missing combos fail closed;
- USA Today discovery finds the new article; fails closed when the
  sitemap has nothing; rejects markup mismatches and thin pages;
- CBS discovery falls back to the latest live week; fails closed when
  none resolve;
- import-health consumption: missing file → pending; ok/stale → landed;
  failed → not landed.

Run: `make test` (or `python3 -m unittest tests.test_pull_watchdog`).

## Schedule

Cron `source-pull-watchdog`, daily 07:05 CT — after the last morning pull
(ECR 06:35 CT). Runs `python3 ops/watchdog/pull_watchdog.py` from the
repo. Silent when green (exit 0); the worker follows the failure path on
exit 1 and escalates only unfixable failures.
