## 2026-10-26 - phone header freshness button (JEG-983 item 2)

Contract: apply Jeremy's 2026-10-25 decision (option C): under 420 px the freshness button stays beside the site name with a short label ("Week 7"), header at most 120 px (JEG-887), 44 px tap target kept (JEG-947). Stacks on PR #948 (JEG-1106 menu).

### Verified (check named)
- Before the change, on the #948 base: tests/test_v2_phone_header_render.py test_wordmark_on_first_paint was red at 360 px (freshness top 52, wordmark top 8).
- After: tests/test_v2_phone_header_render.py passes (3 tests), RENDER_TESTS_REQUIRED=1, 320 to 412 px, both tabs.
- Guards fail against simulated breaks: the test's two CSS patches (button back on its own row; full text instead of "Week 7") each make run_checks non-empty (test_guard_fails_on_broken_builds). The old "freshness back on its own row" patch anchored a rule the menu rebuild had overridden, so it no longer broke anything; I re-pointed it at the new rule. The 120 px limit and all assertions are unchanged.
- tests/test_render_sweep_coverage.py passes with the phone header file wired into Makefile and removed from KNOWN_RED.

### Claimed, not confirmed
- tests/test_v2_phone_tap_targets_render.py is still red on this base for two reasons unrelated to the header: a 768 px trade-targets overlap (source links under the info buttons) and the known Reviewed chip guard gap. Not fixed here; see the new ticket.
- At 320 px the button may wrap to its own row (104 px header, inside the 120 px limit); the test only requires the same row from 360 px.
