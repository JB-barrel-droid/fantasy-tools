## 2026-10-30 - Sleeper identity refresh unblocked: dry run resolves through the saver (JEG-1386)

Contract: the Sleeper identity refresh has failed every scheduled run since
2026-10-13, so roster status, injury status and depth chart in players.json
date from the 2026-10-09 pull (found under JEG-1378: Jalen Hurts still showed
"Active roster", PHI QB1 after going on IR). On main, the refresh's identity
step fails `tests.test_player_identity_guard` twice because
`capture_projections_only.py` (#1199, JEG-1377) injected its own resolver into
`projection_capture.cbs_capture_rows`. The fix moves that one injection into
`save_cbsros_references.capture_rows`, which both the save and the Sunday dry
run call, so the guard's contract is unchanged and the dry run resolves names
exactly as the write does.

### Verified (check named)
- `python3 -m unittest tests.test_player_identity_guard`: 2 failures on main
  (7aa365e: `test_player_resolution_uses_canonical_players`,
  `test_production_injected_resolver_is_canonical`), 26 OK on this branch.
- `tests.test_projection_capture_sunday_jeg1377` and
  `tests.test_projection_captures`: 47 OK (dry-run tests now stub the registry
  fetch and `resolve_name` instead of the removed `_cbs_resolver`).
- The refresh workflow's other identity tests
  (`test_sleeper_identity_layer`, `test_match_identity_keys`,
  `test_source_snapshot_match`): OK.
- `make -k test-core`: every target passes except
  `tests.test_week_history` engine/reference transition, which needs
  Playwright (not installable in this cloud session).
- Value impact, by `rg` over pipelines, app and mcp-server: nothing that
  computes DDF Value, tiers or the lineup parameters the engine reads
  (`config/lineup_parameters.json`) reads Sleeper injury status or depth chart
  at build time.

### Claimed, not confirmed
- After merge, a manual dispatch of `sleeper-identity-refresh.yml` passes and
  moves `meta.pulled_at` past 2026-10-09 (needs the merge first).
- Fresh Sleeper data changes display labels, waiver "your starter is Out"
  notes and stash/handcuff signals (outside DDF Value); not measured, since
  Sleeper's API isn't reachable from this session.
- `derive_lineup_parameters.cross_source_sigma` excludes unavailable players
  from the measured sigma; it runs only by hand and reaches
  `config/lineup_parameters.json` only through a manual, Jeremy-approved
  change.
