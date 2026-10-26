## 2026-10-25 - Red-test triage (JEG-1075, JEG-981, JEG-982, JEG-983)

Contract: re-run the listed red tests on origin/main (06c9be24), decide code vs test per failure, guard the unguarded Playwright import.

### Verified (check named)
- JEG-981: `python -m unittest tests.test_audit_pie` with RENDER_TESTS_REQUIRED=1: 41 tests OK. Already fixed by 826c8dd4 (selector now `h2, h3, h4`).
- JEG-982: `python -m unittest tests.test_endpoint_parity` (RENDER_TESTS_REQUIRED=1): 4 tests OK, wired at Makefile line 129. No mismatch on current main; the 185-player gap predates the JEG-1031 rework of the edge runner (192dda71, #898). Not diagnosed further.
- JEG-983 item 1: tests/test_v2_circular_banner_render.py no longer exists (deleted by 624172f2, banner retired, JEG-921).
- JEG-983 item 5: `tests.test_v2_phone_tap_targets_render` main test passes; only `test_guard_fails_without_jeg1048_fixes` fails (small Reviewed chip not caught). That is JEG-1048 territory, not touched.
- JEG-983 item 4: code is right (`#v2OpenHint` is a `.v2-sr` visually hidden span, 1px clip). Test filter now skips `.v2-sr`. `tests.test_v2_writing_subtabs_order_render` 2 tests OK including its broken-order guard.
- JEG-983 item 3: code is right (JEG-899 roving tabindex sets cells to tabindex -1; one tab stop per row; ArrowRight enters cells). Assertion now accepts tabindex "0" or "-1". `tests.test_v2_source_links_render` 2 tests OK. The cell still must carry aria-describedby=v2MathTip and focus must show the tip (unchanged).
- JEG-1075: with a stub `playwright` package that raises ImportError on PYTHONPATH, `tests.test_value_overrides` errored before the fix; after: skipped locally, and an error under RENDER_TESTS_REQUIRED=1.

### Claimed, not confirmed
- JEG-983 item 2 (phone header) left red on purpose: at 360-412 px the freshness button is on its own row (JEG-953 hamburger CSS, v2.css `@media (max-width: 419px)`), and the header is 148 px, over the test's 120 px limit. This is the layout JEG-887 complained about, so code or test being stale is a product call. Question is on the ticket.
