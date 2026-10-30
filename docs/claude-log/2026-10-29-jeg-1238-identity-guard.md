## 2026-10-29 - JEG-1238 identity guard regression blocking Sleeper refresh

Contract: make `tests.test_player_identity_guard` tell an injected resolver
parameter from an unbound global, without weakening canonical identity
enforcement, so the Sleeper identity refresh's test step stops failing on a
false positive. Guard and its tests only; no production code, workflow,
Supabase or refresh run.

Cause: JEG-944 (#849, 2026-10-23) added `pipelines/lib/projection_capture.py`,
whose `cbs_capture_rows(ros_rows, weekly, resolve, ...)` calls its `resolve`
parameter. The guard only knew module-level imports and defs, so it read the
parameter as a bare global and failed `test_player_resolution_uses_canonical_players`.
`sleeper-identity-refresh.yml` runs that suite in "Identity tests against the
new base" before its commit step, so the refresh stopped there.

### Verified (check named)
- Before: main a75b6a28 `python3 -m unittest tests.test_player_identity_guard`
  fails 1 of 12 (`test_player_resolution_uses_canonical_players`, projection_capture.py).
- Provenance (AST trace `injected_resolver_wiring`, plus reading the code):
  the only pipeline caller of `cbs_capture_rows` is
  `pipelines/save_cbsros_references.py:258` (`save_captures`, also reached from
  `capture_projections_only.py`), passing a lambda over `resolve_name`, which
  calls `canonical_players.resolve_with_reason` against the `public.players`
  registry. The other caller is the stub in `tests/test_projection_captures.py`
  (tests are not scanned).
- After: `tests.test_player_identity_guard` 17 PASS; `tests.test_sleeper_identity_layer`,
  `tests.test_match_identity_keys`, `tests.test_source_snapshot_match` PASS
  (the workflow's four identity modules). No new issue anywhere else in pipelines/.
- Mutations of the guard itself all fail the suite: permit-all wiring check
  (8 failures), dropping the caller-wiring and no-caller checks (13), counting a
  rebound parameter as injected (1).
- Mutations of the real files fail: caller injects `str(n).lower()`, caller adds
  `or 0` fallback, `resolve_name` stops calling canonical_players, caller removed.

### Claimed, not confirmed
- The next Sleeper refresh passes its test step: not run here (no dispatch/rerun
  authorized; coordinator owns recovery).
- `tests.test_projection_captures` `test_real_history_counts` fails the same way
  on main (week-8 history file present, test pins weeks 2-7); unrelated, untouched.
