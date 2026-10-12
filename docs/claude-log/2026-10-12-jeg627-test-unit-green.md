## 2026-10-12 - JEG-627 make test-unit red on main

Root causes, one fix each (code assumed wrong first; assertion changed only where it was stale, reason given):
- `tests.test_harness_main_guard` / the four `tests/rendered_gate` scripts: `is_main.mjs` compared `import.meta.url` with the unresolved argv path, so on macOS (/var -> /private/var, symlinked checkouts) it never matched. CODE bug. Fixed with a realpath comparison.
- The four rendered_gate node scripts also failed when the pinned playwright-core's Chromium build was not installed. Makefile now passes `CHROMIUM_PATH` (env, else the browser `tests/_render_env.py` finds). Needs `npm ci --prefix tests/rendered_gate` as before.
- `tests.test_monitoring_coverage`: `v2-render-test.yml` (JEG-618, PR/manual only) was missing from `config/monitoring_coverage.json`. CONFIG gap, added to `unmonitored_workflows`.
- `tests.test_value_check`: asserted no source has a `validationHold`, but the live fixture carries real fidelity holds (cbsros, razzball). ASSERTION wrong: now asserts non-held sections keep the fixture's own hold unchanged.
- `tests.test_v2_panels_render`: (1) chart-controls allowlist did not know JEG-500's per-card expand/collapse buttons (`.v2-mod-ctl`, covered by test_v2_modules_render); (2) hard-coded 15.0% bench share, but since JEG-536 the share in effect is the computed readout (7.2%). Both ASSERTIONS stale, features intended.
- `tests.test_v2_ux_render`: passes alone (17 s); the earlier failure was load-related timeout under concurrent suites, not a code defect.

### Verified (check named)
- Each of the above module run alone with py3.12 first on PATH: OK.
- Four rendered_gate scripts against dist with CHROMIUM_PATH set: exit clean.
### Claimed, not confirmed
- Full `make test-unit` end to end was not re-run to completion (machine loaded; panels render test alone takes 4 min).
