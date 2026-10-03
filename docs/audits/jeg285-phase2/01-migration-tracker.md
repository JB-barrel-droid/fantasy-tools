# JEG-285 Phase 2 — Migration Tracker

**Status legend:** `NOT STARTED` → `SHADOW` → `CUT OVER` → `VERIFIED` → `DECOMMISSIONED`

Shadow = new path runs in parallel with old, outputs compared, old still authoritative.
Cut over = new path is authoritative, old disabled but recoverable.
Verified = new path proven stable over N cycles, old implementation archived.
Decommissioned = old implementation removed.

## Scheduling migrations (GitHub cron → pg_cron)

| # | Workflow | Current trigger | Target | Status | Shadow plan | Cutover gate |
|---|---|---|---|---|---|---|
| 1 | `source-vintage-check` (hourly) | GHA cron `0 * * * *` | pg_cron + SQL/Edge Function | SHADOW (2026-10-03, job `vintage-check-shadow` live) | Run pg_cron job hourly alongside GHA; compare dispatch decisions for 72h | 72h of identical dispatch decisions, zero missed triggers |
| 2 | `rebuild-chain` trigger (6-hourly) | GHA cron `17 */6 * * *` + vintage-check dispatch | pg_cron → repository_dispatch | SHADOW (2026-10-03, job `rebuild-chain-shadow` live) | pg_cron dispatches to a no-op Action run; verify dispatch fires on schedule | 3 consecutive on-time dispatches matching the 6h cadence |
| 3 | `player-trace-rebuild` (6-hourly) | GHA cron `47 */6 * * *` | pg_cron → repository_dispatch | SHADOW (2026-10-03, job `trigger-player-trace-shadow` live) | Same as #2 | Same as #2 |
| 4 | `espn-supabase-sync` (daily) | GHA cron `30 11 * * *` | pg_cron → repository_dispatch | SHADOW (2026-10-03, job `trigger-espn-sync-shadow` live) | Same pattern | 3 consecutive on-time dispatches |
| 5 | `cbsros-supabase-sync` (weekly) | GHA cron `0 11 * * 3` | pg_cron → repository_dispatch | SHADOW (2026-10-03, job `trigger-cbsros-sync-shadow` live) | Same pattern | 2 consecutive on-time dispatches (weekly cadence) |
| 6 | `fantasycalc-drift` (daily) | GHA cron `45 11 * * *` | pg_cron → repository_dispatch | SHADOW (2026-10-03, job `trigger-fantasycalc-drift-shadow` live) | Same pattern | 3 consecutive on-time dispatches |
| 7 | `live-page-synthetic` (daily) | GHA cron `0 6 * * *` | Edge Function (full move, no Action) | SHADOW (2026-10-03, job `live-page-synthetic-shadow` live) | Edge Function runs daily alongside GHA; compare verdicts for 7d | 7d of matching verdicts |

## Compute (stays on GitHub Actions — no migration)

| Workflow | Why it stays | Notes |
|---|---|---|
| `espn-supabase-sync` pull+save | Python scraping, /tmp file IO | Only the *trigger* moves to pg_cron |
| `cbsros-supabase-sync` pull+save | Python HTML scraping | Only the *trigger* moves to pg_cron |
| `fantasycalc-drift` refresh | Python, file IO, delete+insert | Only the *trigger* moves to pg_cron |
| `rebuild-chain` | 3–10 min Python, filesystem state | Only the *trigger* moves to pg_cron |
| `player-trace-rebuild` | Python JSON processing | Only the *trigger* moves to pg_cron |
| `pages.yml` | GitHub Pages is GitHub-native | No change |
| `preview.yml` | PR-triggered, Playwright/Chromium | No change, no schedule to migrate |

## New capabilities (not migrations)

| # | Capability | Target | Status | Depends on |
|---|---|---|---|---|
| 8 | Chain failure notification | DB webhook → Slack/Discord | DROPPED (2026-10-03, Jeremy: not needed — GH Actions email + Roman monitoring cover it) | N/A |
| 9 | pg_cron retention policy | `cron.job_run_details` cleanup job | DONE (2026-10-03, job `cron-retention-30d` live) | None — do first |
| 10 | Audit-table migration | `001_pipeline_write_audit_repair.sql` | DONE (already live — verified 2026-10-03, columns present) | N/A |

## Prerequisites order

1. Audit-table migration (Jeremy approval) — every save 400s until this runs
2. pg_cron retention policy — before any pg_cron job goes live
3. Webhook URL (Jeremy decision) — before notification work
4. Shadow migrations #1–7 in order listed (lowest risk first)
