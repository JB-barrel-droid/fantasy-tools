# Fantasy Tools Migration

This repository is the migration target for the fantasy-football Trade Value Dashboard currently running in Muse.

Current status: the Muse export has been imported into `app/trade-value-chart/` with current finished data fixtures under `data/fixtures/current/`.

## Goals

- Preserve the current Muse dashboard as the reference implementation.
- Reproduce the current Trade Value Dashboard outside Muse using the existing finished data artifacts first.
- Keep Supabase as the production database.
- Move calculations and collectors out of Muse incrementally only after equivalence tests exist.

## Working with AI sessions

`CLAUDE.md` holds the working agreements — most importantly, that every session
writes its own log entry in `docs/claude-log/YYYY-MM-DD-<slug>.md` before it
finishes, separating what it verified from what it only claimed. The format and
rules are in `docs/claude-log/README.md`. Browse the directory to see what the
last session measured, what it asserted without checking, and what is still open.
(`docs/claude-log.md` is the frozen archive of entries before 2026-10-07.)

## Structure

- `app/trade-value-chart/` - the dashboard source: `index.html` plus `assets/`.
- `dist/` - generated. Exactly what GitHub Pages publishes; never edit by hand.
- `data/fixtures/current/` - the finished artifacts everything else builds from.
- `data/inputs/`, `data/raw/` - vendored source inputs and raw pulls (`raw/` is ignored).
- `pipelines/` - build and data-artifact generation steps; shared helpers in `pipelines/lib/`.
- `modules/` - internal monitor pages, published to `dist/modules/`: `status.html` (ops dashboard, start here) and `dashboard.html` (data monitor drill-down).
- `ops/watchdog/` - source-pull watchdog and per-source ingesters.
- `weekly_vegas/` - Weekly Vegas dashboard (Vegas-vs-ECR disagreement signals) + its build pipeline (bin/, collectors/, engine/, v4/, loaders/, sql/, docs/, research/); a segmented sibling tree to the trade-value chart, not part of it. See `weekly_vegas/README.md`.
- `waiver_wire/` - Waiver dashboard (weekly add / don't-add / drop board) + its build pipeline (bin/, engine/, sql/); a segmented sibling tree to both the trade-value chart and `weekly_vegas/`. Its only cross-tree relationship is a read-only input from the published chart fixture `data/fixtures/current/players.json`. See `waiver_wire/README.md`.
- `tests/` - regression and golden-output tests.
- `docs/` - migration documentation and status.
- `AGENTS.md` - durable project guidance for ChatGPT/Codex, Claude Code MCP,
  Muse.ai/Muse, validation, and GitHub handoffs.

An earlier plan also called for top-level `trade_value/` and `shared/` packages.
Neither was ever used: domain logic lives in `pipelines/` and the shared identity,
scoring, and naming helpers live in `pipelines/lib/`. The empty placeholders were
removed rather than left standing as structure that does not exist.

## Local Run

Serve the static dashboard locally:

```bash
make serve
```

Then open:

```text
http://localhost:8000
```

## Tests

Run the normal validation path:

```bash
make validate
```

That validates the finished reference artifacts, syncs them into the static
dashboard output, and runs the regression tests.

Run the current dependency-free regression checks:

```bash
make test
```

Run chart/value diagnostics without launching a browser:

```bash
make diagnostics
```

Use this when local Playwright/Chromium is blocked by the host sandbox. It runs
the Node harness and fixture integrity checks that cover the chart value model,
adjusted-source availability, anchor scaling, and CBS no-imputation behavior.

Check reference freshness without mutating source artifacts:

```bash
python3 pipelines/check_reference_freshness.py --today YYYY-MM-DD
```

The report is written to ignored `output/reference-freshness.json` and records
when a reference date is unchanged from the prior run. By default the production
gate enforces `comparison.built_at`, while legacy/player/news timestamps remain
visible in the report.

```bash
make freshness-check MAX_STALE_DAYS=2
```

`make validate` runs this gate before syncing `dist/`, and the GitHub Pages workflow also runs on a daily schedule so stale artifacts cannot keep deploying silently.

Import a scraped trade-value page from Muse or another scraper into the standard
raw source format:

```bash
make source-import SOURCE_FILE=/path/to/scrape.csv SOURCE=fantasycalc SCORING=ppr TEAMS=12
```

Match an imported source snapshot to canonical player keys:

```bash
make source-match SNAPSHOT_FILE=data/raw/sources/fantasycalc/2026-09-21/fantasycalc-ppr-12-2026-09-21T120000z.json
```

Build a source-reference artifact from matched rows:

```bash
make source-reference MATCH_FILE=output/source-matches/fantasycalc/2026-09-21/fantasycalc-ppr-12-matched.json
```

Build a candidate comparison section and merge it into an output-only candidate:

```bash
make source-section REFERENCE_FILE=output/source-references/fantasycalc/2026-09-21/fantasycalc-ppr-12-reference.json
make comparison-candidate SECTION_FILE=output/comparison-source-sections/fantasycalc/2026-09-21/fantasycalc-ppr-12-section.json
```

The player-news pipeline (`ingest_player_news.py`, `make source-news`) was
retired 2026-10-08: it had no producer outside a local raw folder. Revive it
from git history (last present at `aefb8f7`) if news comes back.

Sync the finished fixtures into the static dashboard and deployable `dist/` output:

```bash
make sync
```

## Modular Pipeline

The project should move in four stages:

```text
source data -> reference compute -> dashboard build -> frontend/site
```

- `source data`: collect raw snapshots from feeds, public pages, APIs, or Muse.
- `reference compute`: turn raw/source snapshots into stable fixtures under
  `data/fixtures/current/`.
- `dashboard build`: copy finished fixtures into `app/trade-value-chart/` and
  `dist/`.
- `frontend/site`: display the finished artifacts and handle user interaction.

See `docs/modular-pipeline.md` for the working boundary rules.

## Development Workflow

ChatGPT/Codex remains the project hub and final integrator. Long-running
reasoning, architecture/design exploration, code review, debugging
investigations, and other token-intensive work should be delegated to Claude Code
MCP when available. Muse.ai/Muse should be used where it creates concrete value
with low overhead, especially raw source capture, reference-dashboard
comparison, research sweeps, and UI/design exploration.

Use `AGENTS.md` for standing project-agent instructions and
`docs/delegation-workflow.md` for delegation and handoff templates. GitHub should
stay current enough that switching between ChatGPT/Codex, Claude, Muse, or
another harness costs no more than about 10-20 minutes.

## Publishing

There is one publish path. Pushing to `main` runs `.github/workflows/pages.yml`,
which runs `make validate` and deploys `dist/` to GitHub Pages.

`make validate` is the same gate locally: it checks naming drift, validates the
reference artifacts, regenerates `dist/` from `app/` and the current fixtures,
and runs the test suite. Because `sync` regenerates `dist/`, editing anything
under `dist/` by hand is always wrong -- edit `app/trade-value-chart/` (or the
fixtures) and re-run `make sync`.

After a deploy, confirm the live site matches the repo:

```bash
python3 verify_live.py
```

## Secrets

Do not commit `.env`, Supabase keys, service-role keys, cookies, browser sessions, FantasyPros credentials, or any raw private export containing secrets.
