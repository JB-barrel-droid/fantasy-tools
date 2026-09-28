# Current Plan

This is the only live plan file. Keep it short; move completed investigation
details to `docs/claude-log.md` and durable gaps to `docs/risk-register.md`.

## Objective

Make repo memory explicit enough that future sessions do not rediscover the
same gaps, then close the highest-confidence gaps directly in code/docs.

## Active Workstream

Gap cleanup and record keeping.

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

## Current State

The code-level cleanup items are closed. A source-refresh dependency is now
open because the canonical freshness gate marks the comparison artifact stale
on 2026-09-28; see `GAP-007` in `docs/risk-register.md`.

## Operating Rule

Do not add a second backlog, plan, or gap tracker. Use:

- `execution/current-plan.md` for the live task list.
- `docs/risk-register.md` for durable gaps and follow-ups.
- `docs/claude-log.md` for session evidence.
