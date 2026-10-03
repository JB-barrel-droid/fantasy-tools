# JEG-285 Phase 2 — Target Architecture Decision

**Status:** Approved by Jeremy 2026-10-03
**Decision:** Option C — Supabase-native scheduling + notifications, GitHub Actions for heavy Python compute. No Pipedream. No new infrastructure.

## The shape of the answer

Each layer of the stack does what it's best at. Nothing new is attached.

| Layer | Owns | Why it wins |
|---|---|---|
| **Supabase pg_cron** | All scheduling | Native to where the data lives; kills the B7 trigger-loop risk (hourly `source-vintage-check` as the real chain trigger, invisible to GitHub) |
| **Supabase webhooks** | Failure notifications | Async, event-driven; fixes the "no notify on red chain" gap |
| **Supabase Edge Functions** | Lightweight HTTP checks | `live-page-synthetic`, `fantasycalc-drift` check — well under the 2s CPU cap |
| **GitHub Actions** | Heavy Python compute | 6-hour job limit, full filesystem, free, already working — beats every alternative for the 3–10 min chain |
| **Pipedream** | Nothing | Ruled out by Jeremy 2026-10-03 |

## Why not Pipedream (recorded for the audit trail)

- Paid tier caps at 750s per execution; the 6-hourly chain runs 180–600s — fits barely, no headroom
- Free tier caps at 300s — the chain doesn't fit at all
- No persistent filesystem — the chain's snapshot/fixture state would need migrating into Supabase first
- GitHub Actions beats it on every dimension that matters here: longer limit, free, filesystem intact, zero migration cost

## Why not Supabase Edge Functions for compute

Confirmed from official docs 2026-10-03:
- **2 seconds max CPU time** per request (the binding constraint, not wall-clock)
- 400s wall-clock on paid plans, 256MB memory
- SMTP ports 25/587 blocked — notifications must go through a third-party API or webhook (Slack/Discord), not direct email
- No multithreading, no Web Workers
- Python is not available — the scrapers and chain are Python

## Workflow-by-workflow mapping

| Workflow | Target | Notes |
|---|---|---|
| `source-vintage-check` (hourly) | pg_cron + SQL | Pure vintage comparisons; this is the B7 fix — the trigger moves into the database |
| `live-page-synthetic` (daily) | Edge Function | HTTP fetch + string check |
| `fantasycalc-drift` check | Edge Function | Lightweight API comparison; the refresh step stays Python on Actions |
| `espn-supabase-sync` pull | GitHub Actions (unchanged) | Python scraping + file IO |
| `cbsros-supabase-sync` pull | GitHub Actions (unchanged) | Python HTML scraping |
| `rebuild-chain` (6-hourly) | GitHub Actions (unchanged) | 3–10 min Python; triggered by pg_cron via repository_dispatch or workflow_dispatch |
| `player-trace-rebuild` | GitHub Actions (unchanged) | Python JSON processing |
| Chain failure notify | DB webhook → Slack/Discord | Fires on red chain status; retry behavior undocumented — treat as best-effort, not guaranteed |
| `pages.yml` deploy | GitHub Actions (unchanged) | GitHub Pages is GitHub-native |
| `preview.yml` PR previews | GitHub Actions (unchanged) | Needs Playwright/Chromium |

## Prerequisites (before any cutover)

1. **Audit-table migration** — `sql/migrations/001_pipeline_write_audit_repair.sql` must run first. Every save currently 400s on `WriterAudit.start()` because the live table lacks `code_revision` and `error_message`. **Requires Jeremy's explicit approval** (the migration labels itself DO NOT EXECUTE without review).
2. **pg_cron retention policy** — `cron.job_run_details` is never cleaned up automatically. Set a retention policy or it grows unbounded.
3. **Chain trigger mechanism** — pg_cron must be able to trigger the GitHub Actions chain (repository_dispatch via pg_net, or a lightweight Edge Function that calls the GitHub API). The trigger path itself must be monitored.
4. **Notify webhook target** — pick the Slack/Discord webhook; SMTP is blocked so email needs a third-party API.

## What stays parked

- Dagster / control-plane decision — only if Supabase Cron + persisted state tables prove insufficient (per the Phase 3 gate in the ticket)
- Phases 3–5 of the original ticket scope

## Guardrails (from the ticket, still binding)

- No big-bang rewrite; migrate incrementally, lowest risk first
- Do not delete working GitHub workflows before the replacement is validated
- Shadow-mode the pg_cron triggers before cutting over (run old and new schedules in parallel, compare)
- Preserve production outputs throughout unless separately approved
