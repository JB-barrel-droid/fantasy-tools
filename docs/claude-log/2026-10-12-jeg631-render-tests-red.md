## 2026-10-12 - JEG-631 render tests red on main after JEG-500

Contract: root-cause the red render suites on main and fix forward (code assumed wrong first).

Root causes:
- `tests.test_v2_waterfall_render` (CODE bug, JEG-505): the verdict's headline rows use class `v2-chead`, which the Compare card head already styles as `display:flex; space-between; wrap`. The "Should you propose or accept? / Yes / confidence" rows were split across the card and the card grew ~54 px. Fix in `app/v2/v2.css`: `display:block` on `.v2-cheads .v2-chead`. Even then the card ended at 779 px on a 768 px screen, so at >= 1280 px the verdict column is wider (`minmax(420px, 1.6fr)`, give/receive columns are mostly empty) and the verdict gaps are tighter. The test's mutation anchor for "no 3-column layout" was updated to the new column string (anchor text only; the check itself is unchanged and still fails the broken build).
- `tests.test_v2_targets_render` toggle check (ASSERTION too broad): `#v2Targets [aria-pressed]` also matched JEG-500's per-card expand button (`.v2-mod-btn`), which is not a Sell/Buy toggle. Selector now excludes `.v2-mod-btn`; real `button[data-side]` toggles still fail it.
- `tests.test_v2_targets_render` opened-row native rank (ASSERTION wrong): the test simulates a chart value the engine lacks (a null value with a reason) but the engine still holds that player's real native rank. The app shows the reason, not a rank, for a cell with no value (correct). Which row is simulated shifts with data (JEG-535), so it surfaced now. The check now expects no native rank on a `missing` cell; the "native rank off by one" mutant is still caught on every other cell.
- `tests.test_trade_chart_ingest_ci` (3 errors): `Path.write_text(newline=)` is Python 3.10+; the bare `python3` here is 3.9.6. Test now writes the stub with `write_bytes` (LF on any OS/version).
- `tests.test_v2_panels_render`: already green on main (fixed by JEG-627 in #561).

### Verified (check named)
- Reproduced on origin/main with py3.12 first on PATH: targets (1 fail), waterfall (1 fail), panels OK, ingest OK on 3.12 and 3 errors on 3.9.
- After the fix: `tests.test_v2_targets_render`, `test_v2_waterfall_render`, `test_v2_panels_render`, `test_v2_modules_render` all OK (8 tests, py3.12); `tests.test_trade_chart_ingest_ci` OK on python3 3.9.6 and 3.12.

### Claimed, not confirmed
- No numbers change (CSS and tests only); no engine_dump sweep run. Full `make validate` still has the unrelated JEG-630 bench-share failure noted in the JEG-627 entry.
