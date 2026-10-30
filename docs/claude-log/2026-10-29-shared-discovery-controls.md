## 2026-10-29 - Shared discovery controls (JEG-1320)

Contract: slice 1 of `docs/specs/trade-page-parity.md` (6.2). One pure module, `app/v2/discovery-controls.js`, that
normalizes the finders' discovery controls into one record and migrates both stored shapes, with D3 pick A (the
your-team finder's `ui.finderSettings.maxSize` wins; `ui.maxSize` is dropped). No route reads it yet (JEG-1321,
JEG-1322). No value, default or listing change.

### Verified (check named)
- `node tests/node/discovery_controls_check.cjs`: 16 passed, 0 failed. Run through `python3 -m unittest
  tests.test_jeg1320_discovery_controls` (wired into `make test-unit-modules`).
- The check fails when a route default changes. Each mutation below was applied, the check run, and the file restored:
  workspace finderSettings default size 3 (4 cases fail), league `ui.maxSize` default 3 (2 fail), keep-my-lineup
  default off (4 fail), league search keep flag off in `league.js` (1 fails), finder page `viableOnly: true` (1 fails),
  league `hideForce` default on (2 fail). With the module absent the check exits 1.
- `node tests/node/trade_context_check.cjs`: 27 passed, 0 failed (unchanged; the new module agrees with its pair and
  league controls on every shared field).
- `make validate` locally: every step passed except `tests.test_week_history` engine-vs-reference, which needs the
  `playwright` Python module that this cloud container lacks (ModuleNotFoundError). Not touched by this change.

### Claimed, not confirmed
- `make validate` green in CI on the PR head (read from the PR checks, not run here).
- The filter rules duplicate `trade-context.js` `routeControls` (same code, pinned equal by the check). Folding
  `routeControls` onto this module belongs to JEG-1321, since `trade-context.js` is held by #1147.
