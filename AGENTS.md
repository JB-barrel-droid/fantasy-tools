# Fantasy Tools Agent Guide

This repo is the shared working memory for the fantasy football tools. GitHub is
the source of truth for code, project rules, and handoffs; no chat thread or LLM
session is allowed to be the only holder of process memory.

## Operating Model

| Work type | Default route |
| --- | --- |
| Orchestration, final decisions, implementation, validation, handoffs | ChatGPT/Codex |
| Architecture/design options, code review, broad debugging, migration analysis | Claude Code MCP |
| Raw scraping, reference-dashboard comparison, research sweeps, visual exploration | Muse.ai/Muse |
| Small obvious fixes, narrow docs edits, simple command checks | ChatGPT/Codex directly |

- ChatGPT/Codex is the hub and final integrator. It frames tasks, chooses what
  to delegate, supplies enough context, reviews delegated output, makes final
  decisions, edits the repo, validates changes, and keeps GitHub current.
- Claude Code MCP is the preferred delegate for token-intensive work when it is
  available: long reasoning, architecture/design exploration, code review,
  debugging investigations, broad repo searches, migration planning, and second
  opinions before risky changes.
- Muse.ai/Muse tooling is useful when its abundant usage can produce concrete
  project value: source scraping, raw data capture, UI/design exploration,
  quick prototypes, research sweeps, and comparisons against the current Muse
  reference dashboard.
- Avoid delegation for small edits, obvious fixes, simple command checks, or any
  handoff where writing the brief would take longer than doing the work.

## ChatGPT/Codex Responsibilities

- Own the task brief and success criteria before delegating.
- Keep delegated tasks narrow, context-rich, and output-oriented.
- Treat all delegated results as recommendations or raw material, not binding
  decisions.
- Re-read touched files locally before integrating outside output.
- Preserve the repo's fail-closed data rules in `docs/pipeline-rules.md`.
- Run the appropriate validation path before declaring work complete.
- Commit and push coherent, validated slices often enough that another harness
  can continue within about 10-20 minutes.

## Claude Code MCP Use

Use Claude Code MCP for work that benefits from a separate long context window
or independent review, especially:

- investigations spanning several files or subsystems
- changes to pipeline rules or promotion paths
- architecture or data-pipeline design options
- debugging a failing test or data mismatch
- code review before promotion, deployment, or broad refactors
- finding consequences of a proposed schema, fixture, or UI change
- summarizing a large subsystem before ChatGPT/Codex edits it

When starting Claude Code through `claude-code-mcp`, pass `allowedTools` with at
least `Read`, `Edit`, `Write`, `Glob`, `Grep`, and `Bash`. If the desired role is
review-only, say "do not edit files" in the prompt rather than starving the
session of normal project tools.

Claude handoffs should request one of these output shapes:

- findings with file/line references
- options with tradeoffs and a recommendation
- a minimal patch plan
- a reproduction/debugging trace
- a concise risk list and test suggestions

ChatGPT/Codex must make the final call and perform or coordinate the final repo
change.

Claude Code should not push to `main` or trigger deployment autonomously. GitHub
Pages deploys from `main`, so ChatGPT/Codex or the human operator owns that final
publish decision.

## Muse.ai / Muse Use

Muse can collect and explore; the repo decides, computes, tests, and publishes.

Good Muse tasks:

- scrape difficult source pages and return raw CSV/JSON snapshots
- compare the GitHub Pages dashboard against the Muse reference dashboard
- explore UI variants or dashboard interaction ideas
- do broad research where perfect reproducibility is not required
- produce raw observations that can be imported through documented repo commands

Muse output is untrusted input until it passes the repo pipeline. Raw data enters
through the documented import, match, reference, review, and validation steps.
Muse should not be the only place where a collector, formula, decision, or runbook
lives.

Do not ask Muse to resolve canonical player identity, edit fixtures, triage
`review_rows`, or decide promotion readiness. Those steps belong to the
deterministic repo pipeline and human-reviewed validation path.

## GitHub Continuity Rule

Keep `main` and any active branch current enough that switching between
ChatGPT/Codex, Claude Code, Muse, or another harness costs no more than roughly
10-20 minutes.

Practical standard:

- Start work by checking local status and recent commits.
- Prefer small commits after a coherent behavior or documentation slice passes
  validation.
- Push validated commits promptly when the slice is meant to be shared.
- If a slice cannot be committed yet, leave an explicit handoff note in the task
  summary or an appropriate doc with current state, changed files, commands run,
  failures, and next action.
- Do not leave important decisions only in chat.

## Validation

Default validation:

```bash
make validate
```

For narrower work, run the smallest meaningful command first, then run
`make validate` before publishing or promoting data.

`dist/` is generated; edit source files or fixtures, then run the
sync/validation path.

## Handoff Templates

Detailed delegation templates live in `docs/delegation-workflow.md`.

## FantasyCalc drift auto-trigger (2026-09-30)
- Standing rule (Jeremy): the project reruns the FantasyCalc pipelines when
  native doesn't match live. `pipelines/check_fantasycalc_drift.py` compares
  the live API (top-25 by value) against the snapshot's native_value; if >20%
  moved by >5%, it exits 1. With `--trigger` it refreshes the snapshot from
  the live API and runs match -> reference -> section -> reindex -> fixture
  -> monitors automatically. (Thresholds tuned 2026-09-30: FantasyCalc updates
  through the day, so 1-3% intraday moves are normal noise — the 5%/20%
  bands prevent constant refresh churn while still catching real corruption
  like the JSN defect.)
- The 2026-09-30 JSN defect proved why: `match_source_snapshot.py` was
  dropping `native_value`, so the pipeline used the flattened `value` (50.7)
  instead of the raw FantasyCalc number (9914). The matcher and
  `build_source_reference.py` now carry `native_value` through every stage.
- Regression tests: `tests/test_fantasycalc_drift.py` (5 tests).
- Refresh schedule: GitHub Actions workflow `.github/workflows/fantasycalc-drift.yml`
  runs daily at 11:45 UTC (6:45 AM CDT). If drift is detected, it refreshes
  the snapshot, re-runs the pipeline, re-imports to Supabase via
  `pipelines/refresh_fantasycalc_supabase.py`, verifies health, and pushes.
  No local cron — project rules require GitHub Actions for scheduled work.

## As-published indexing: proportional scaling (2026-09-30)
- User directive: "there is no need for rounding like this, so figure out a logic that applies to all the ones sourced from trade value charts." The per-position quantile mapping was destroying real value differences (Jeanty 6365 vs Cook 7157 → both 41.4) and scrambling cross-position rank.
- New logic in `pipelines/reindex_comparison_section.py`: sources with `value_provenance == "published"` (FantasyCalc, USA Today, FantasyPros, CBS) use GLOBAL proportional scaling instead of per-position quantile mapping.
- Formula: `indexed = native × (anchor_total / native_total)` over shared players. This preserves exact value ratios (Cook 12.4% above Jeanty stays 12.4% above), cross-position order, and all differences. No quantile mapping, no rounding in storage.
- Fixed-pie invariant holds: sum(indexed) = anchor_total by construction.
- DDF-methodology sources (ESPN) keep the per-position quantile mapping.
- Verified: Jeanty 6365→42.36, Cook 7157→47.63 (ratio 1.1244 preserved); Taylor 70.0→51.71, Walker 57.9→42.77 (ratio 1.209 preserved).

## VORP>0 overlap calibration (2026-09-30 PM)
- Refinement to as-published proportional scaling (Jeremy): "players with vorp>0 should all add up to the same amount. Some trade charts don't go as deep into vorp>0, but they'll all have overlapping players for the first 50-150, so we can set the index on that set and then use the relative values on the remainder of the chart for the balance."
- Implementation: scale is calibrated on the VORP>0 overlap set (players with anchor_value > 0, typically 150-170 players), not all shared players. The deep tail varies in depth by source and shouldn't drive the scale.
- Formula: scale = sum(anchor_overlap) / sum(native_overlap); indexed = native * scale for ALL priced players.
- Fixed-pie target is the anchor's overlap total; the source's overlap players sum to it.
- Method name: `proportional_scaling_vorp_overlap`. Overlap slugs stored in fit metadata for test verification.

## Lineage rebuild must not run in CI without snapshots (2026-10-01)
- The 09-30 "auto-rebuild source value lineage on every deploy" step runs `build_source_value_lineage.py` in CI, where the gitignored `data/raw` snapshots are ABSENT. The builder silently fell back to TRANSFORMED combo natives and compared live raw values against them: served FantasyPros showed 0/25 live matches (live Gibbs 75.1 vs transformed 88.8) — a monitor false-red caused by the build environment, not the data.
- Fix: `require_snapshot_natives()` in the builder now raises SystemExit when any SNAPSHOT_PATHS source loads zero natives. The write happens at end-of-main, so a CI failure leaves the committed (locally built, correct) `dist/modules/source-value-lineage.json` untouched and the deploy proceeds (step is continue-on-error).
- Rule: any committed `dist/modules/*.json` that CI regenerates must be buildable from repo inputs alone, or the rebuild step must fail closed instead of writing degraded output. Same class as the import-health staleness bug.
- Regression: `tests/test_lineage_snapshot_guard.py` (4 tests: empty refuses, partial refuses, full passes, real local snapshots satisfy — the last is `skipUnless` the gitignored snapshots exist, because a test asserting their presence can never pass in CI; the first version of it failed CI validation and blocked the 3c2136bf deploy). Rebuilt locally 2026-10-01: FantasyPros 25/25, CBS 25/25, FantasyCalc 22/25 (3 genuine intraday moves), USA Today 19/25 + 6 no-live (scrape 402, recorded in live_stale_sources), ESPN N/A-by-design.
- Oddity found during the fix: `data/raw/sources/fantasycalc/week-4/snapshot.json` is force-added to git despite `.gitignore` carrying `data/raw/`; the fantasypros/usatoday snapshots are properly ignored. That's why CI loaded 196 fantasycalc natives while fp/usa loaded 0. Left as-is (removing it would change FantasyCalc lineage behavior); flagging for the next snapshot-management pass.

## CI sync must prefer the freshest health file, not the fixture (2026-10-01)
- The 30-min health cron pushes a fresh `dist/modules/source-import-health.json` with every run, but CI's `make sync` (where the gitignored `output/` runtime file is absent) unconditionally fell back to the committed fixture `data/fixtures/current/source-import-health.json` and OVERWROTE the fresh pushed copy before upload. On 2026-10-01 the served monitor read `checked_at` 08:37Z while main held 10:07Z, because the last three health pushes (4e035da, 46638ad, 28b346f) had stopped including the fixture copy.
- Fix in `pipelines/sync_dashboard_artifacts.py::import_health_source()`: candidates (runtime, checked-in dist copy, fixture) are now ranked by `checked_at` and the freshest valid payload wins; the write step skips the self-copy when the source IS the dist file. Regression: `tests/test_sync_health_freshest.py` (4 tests, incl. a simulation proving the OLD code chose the stale fixture against the broken state), wired into `make validate`'s test-unit list.
- Rule: any committed `dist/modules/*.json` that CI rewrites must resolve to the freshest valid input, never a hardcoded fallback. Both candidates must remain committed: the fixture copy is refreshed by the health runs so the fallback path never drifts by more than one cycle. Note the 30-min cron body itself never contained the fixture-copy step -- the fix makes that omission harmless.
- The fixture was also refreshed to the 10:37Z green gate (6/6 ok) in the same push.

## Watchdog: status marker before content words; repo pulls before legacy cache (2026-10-01)
- `ops/watchdog/_common.py::classify_run_line` used to match the standalone word FAILED before checking the run's status marker (`| OK |`, `SUCCESS`, `no-update`). Razzball's pull log legitimately writes detail notes like "1 rows failed PPG consistency" on an OK run (a tolerated single-row anomaly under the gate threshold), which false-tripped `failed` and then cascaded into a false "CRITICAL: artifact rewritten AFTER the failed run". Rule: status marker wins over detail-text words; genuine `| FAILED |` lines are unaffected. Regression test uses the real 2026-10-01 log line.
- Weekly-article watchdog checks (`check_weekly_article`) read the newest `ops/watchdog/pulls/<src>-<date>.json` first and fall back to the legacy goal-workspace cache. The legacy cache (`lottery/data/sources_cache/*.json`) went dead after the repo ingest pipelines replaced the old lottery pullers (Sep 21); reading it first false-alarmed STALE on CBS/USA Today while Supabase already held fresh rows. When a watchdog source false-alarms stale, check which cache path the watchdog reads before assuming the ingest is broken.
- USA Today 2026-09-29 week-3 article layout note: the QB table sits under the generic "Week N fantasy trade charts" h2 (lazy h2->table pairing); `pull_usatoday.py::_clean_title_position` infers the QB title from the 1QB/6-TD/SFLEX header signature. Also 2026-10-01: curl fetches of usatoday.com article pages now return persistent 402 while sitemap + browser render still work -- if the 402 persists when the week-4 article publishes, the ingest fetch path needs a new strategy.

## cbsros snapshot force-added for CI (2026-10-01)
- `data/raw/sources/cbsros/2026-09-30/snapshot.json` force-added to git (commit ec4f3986), following the fantasycalc week-4 precedent. The rebuild-chain workflow's `find_latest_snapshot()` needs this file in the CI checkout; `data/raw/` is gitignored so CI otherwise has no cbsros snapshot and the chain fails at the cbsros stage.
- cbsros has no Supabase table (unlike the other five sources), so it cannot go through `import_supabase_references.py`. The snapshot is the only CI input path.
- When the snapshot goes stale, refresh via `pipelines/pull_cbs_ros_projections.py` and force-add the new date directory.
