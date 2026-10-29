## 2026-10-28 - JEG-1184 package and bench-depth follow-up

Contract: Jeremy requested an explicit 1-for-1 finder choice and minimum positional bench backups with plus/minus controls. This is a separate follow-up from draft #1068 and integration release #1069.

### Verified (check named)
- `tests.test_v2_finder_guardrails`: 1-for-1 subset boundary, post-trade last-backup rejection, starter/FLEX/superflex allocations counted once, finite zero counted and missing value excluded, default minima 0, bounded settings, save/import and link round-trips.
- `tests.test_v2_finder_guardrails_render` with Chromium: package choice, keyboard increment, persistence, reset and link visit passed at 390 px.
- `tests.test_v2_finder`, `tests.test_v2_league_units`, `tests.test_v2_share_links` passed. Seeded 2-for-2 and 3-for-3 search signatures exactly match the untouched follow-up base.
- `tests.test_v2_finder_groups` fails identically on the untouched follow-up base: the kept trade lacks a named throw-in. This follow-up does not change that test or search logic.

### Claimed, not confirmed
- Integration into #1069, remote CI and live behavior are pending. No production merge or deployment was performed.
