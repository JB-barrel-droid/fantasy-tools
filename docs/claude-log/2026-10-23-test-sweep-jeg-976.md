## 2026-10-23 - JEG-976 test sweep: wire unreferenced tests

Contract: list every file under tests/ that no Makefile target and no workflow runs, run each alone, wire the green ones (CI time under 10%), ticket the red ones without fixing or loosening them.

### Verified (check named)
- Inventory: a script matched each tests/ file name against Makefile plus .github/workflows/*.yml. 90 entries unreferenced; 13 are helpers driven by other tests (`_bash.py`, `_dist_server.py`, `_edge_pipeline_runner.cjs`, `_es_worked_example.py`, `_holds.py`, `_run_lane_protocol.py`, five `*_harness.js`, `two_tier_harness.js`, `value_pipeline_driver.js`), confirmed by grep for their callers. 77 are test files.
- Ran each alone. 31 modules with `python3 -m unittest tests.<name>`: 30 green and `test_audit_pie` (needs a browser, red). 7 more are pytest-style (unittest says "NO TESTS RAN" or fails on `import pytest`), run with `python3 -m pytest`: 6 green, `test_endpoint_parity` red. Browser: `CHROMIUM_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome RENDER_TESTS_REQUIRED=1`, 39 `*_render` files plus `test_audit_pie.py` (34 render files green, 5 red). First pass ran four at a time (timings inflated); every failure was re-run alone, serially. `test_v2_finder_paste_render` failed under load and passed alone (115 s), so it counts green.
- Result: 70 green files (30 unittest, 6 pytest, 34 render), 7 red files: `test_audit_pie`, `test_endpoint_parity`, `test_v2_circular_banner_render`, `test_v2_phone_header_render`, `test_v2_source_links_render`, `test_v2_writing_subtabs_order_render`, `test_v2_phone_tap_targets_render`. Tickets JEG-981 (audit pie), JEG-982 (endpoint parity), JEG-983 (five render files). Nothing fixed or loosened.
- Wired: 28 hermetic unittest modules and 6 pytest modules into `test-unit-modules` (about 20 s together, measured), 7 cheapest green render modules into `test-unit-modules` (about 2.5 min, from the sweep timings), and `test_value_pipeline_engine` plus `test_razzball_outlier_guard` into `test-core` (0.8 s, both hermetic, both pin published numbers). `preview.yml` installs pytest before `make test-unit`. The 37 non-render commands were executed once from the Makefile text after wiring (0 failures apart from `test_audit_pie`, which I then removed because it is red); the 7 render modules were run alone in the sweep but not re-run from the Makefile.
- Broken-state proof: stubbed `razzball_outlier_reason` to return None; `tests.test_razzball_outlier_guard` failed (4 failures of 7); restored, 7 pass.
- `tests.test_run_suite`, `tests.test_validate_runner`, `tests.test_doc_staleness`: 12 tests OK after the Makefile edit.

### Claimed, not confirmed
- CI time: the render modules were timed on this machine, four in parallel for the first pass, so real runner time may differ. The 10% budget was estimated against the 25-55 min preview figure in the brief, not measured on GitHub.
- `make test-unit` was not run end to end (needs a built dist and the node harnesses); only the added lines were run.
- Which side is stale in each red ticket is a read of the diff, not a decision. `test_endpoint_parity` cause is undetermined.
- Not wired for CI budget, green (27 render files, roughly 25 more minutes): listed in the PR table as a follow-up for a dedicated render job. The edge-runner parity test needs the Playwright browser path in `tests/_dist_server.py`, which ignores CHROMIUM_PATH; I linked a browser under /opt locally to run it, nothing in the repo.

### Addendum: render sweep job (Jeremy, 2026-10-23, option b)
- Verified: `make test-render-extra` lists the 27 green render modules (run_suite parses 27 lines); new `tests/test_render_sweep_coverage.py` passes, and with `test_v2_names_render` deleted from the real Makefile it fails naming that file. Also passing: `test_monitoring_coverage`, `test_gha_schedules_pg_cron`, `test_no_failopen_workflows`, `test_run_suite`.
- Not verified: the new workflow was not run on GitHub; the 27 modules were not re-run together from the new target.
- Convention found: schedules are pg_cron dispatching `workflow_dispatch`, so `render-sweep.yml` has no `schedule:`. The pg_cron job `render-sweep-daily` is written in `supabase/render_sweep_pg_cron.sql` and NOT applied (production Supabase change, no database access here); until it is, the sweep only runs when dispatched by hand.
