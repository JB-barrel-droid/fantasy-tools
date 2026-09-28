# Current Plan

This is the only live plan file. Keep it short; move completed investigation
details to `docs/claude-log.md` and durable gaps to `docs/risk-register.md`.

## Objective

Get the gap-cleanup changes live without weakening the source freshness gate.

## Active Workstream

Live deploy unblock.

## Current Tasks

- [x] Restore missing read-first entrypoints: `SYSTEM_MAP.md`,
  `docs/methodology.md`, and this file.
- [x] Make adjusted value logic consistent between the curve widget and
  comparison dashboard.
- [x] Keep `docs/risk-register.md` current whenever a durable gap is discovered,
  fixed, or deliberately deferred.
- [x] Add any remaining validation evidence to `docs/claude-log.md` before
  ending the session.
- [x] Close the remaining open gap-register rows:
  adjustment-cell completeness, same-vintage review methodology, CBS
  no-imputation coverage, and non-browser diagnostics fallback.
- [ ] Restore the missing Supabase import helper (`SUPABASE_FOOTBALL_SIGNAL_BIN`
  / `sbclient`) or supply validated raw source snapshots.
- [ ] Refresh all five comparison sources through the documented pipeline.
- [ ] Run `make validate`, push the validated fixture refresh, and verify the
  GitHub Pages deployment.

## Current State

The code-level cleanup items are closed and pushed. GitHub Pages is not live on
that commit because the deploy workflow fails at `make validate`: the comparison
source fixture is stale on 2026-09-28. A real source refresh is blocked locally
because the Supabase import helper `sbclient` is missing and MCP access is not
available under this task's approval policy; see `GAP-007` and `GAP-008` in
`docs/risk-register.md`.

## Operating Rule

Do not add a second backlog, plan, or gap tracker. Use:

- `execution/current-plan.md` for the live task list.
- `docs/risk-register.md` for durable gaps and follow-ups.
- `docs/claude-log.md` for session evidence.
