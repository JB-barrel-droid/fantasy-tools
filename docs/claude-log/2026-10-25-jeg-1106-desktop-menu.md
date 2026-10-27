## 2026-10-25 - JEG-1106 desktop navigation menu

Contract: replace the ten-tab top bar with a hamburger button that opens a grouped menu (Trade, Players, Auditing, Our approach, Settings) at every width, per Jeremy's 2026-10-25 decisions on the ticket (option A, group named "Our approach", land on the value chart, no recent-tools strip). Stacks on #944 (finder). Does not touch app/v2/finder.js, opportunities.js or the detail panel.

What changed
- app/v2/shell.html: button, site name, current page name, grouped menu (14 entries), freshness button. The menu is still `#v2Tabs` with `.v2-tab` entries (the JEG-953 mechanism), so phones keep working.
- app/v2/v2.js: landing and unknown-hash route is `#player-values`; active entry picked by `data-key` (so Writing and Values auditing sections are separate entries); current page name beside the button; arrow / Home / End keys; Customize opens the sources dialog.
- app/v2/v2.css: button at every width; desktop menu is a floating panel (three columns, max 720 px); one quiet accent (the freshness dot green) marks the page on show. There were no per-tab colors in the existing CSS (the tabs were uniformly white on the dark bar), so nothing to remove there.
- Mapping to confirm with Jeremy: Value pie -> `#values-auditing/health-check`, Source build-up -> `#values-auditing/single-source` (the two existing Values auditing sub-pages); Methodology -> `#writing/how-values`, Research -> `#writing/research`, Manifesto -> `#writing/manifesto`; Customize is a button that opens the sources dialog (not a route).

### Verified (check named)
- tests/test_v2_desktop_menu_render.py (new): 1366x768 and 1000x700 one-row bar, no sideways scroll, menu fits; Enter/Space/arrows/Home/End/Escape/focus return; click, entry navigation, outside tap; aria-expanded, one aria-current, labelled groups; 21 deep links incl. #find-trade, #find-league, legacy #manifesto/#how-values/#research, #values-auditing/value-pie, empty and unknown hash; Customize dialog. Negative test: 9 simulated breaks (no arrows, no Escape, no aria-expanded, no aria-current, no page name, old landing, Customize inert, menu wider than screen, menu in the bar) each fail it.
- tests/test_v2_hamburger_nav_render.py (phone checks kept; new 14 labels; wide screens now check the button is present and the menu starts closed): pass, 6 mutation subtests pass.
- tests/test_v2_waterfall_render.py test_no_sideways_scroll_with_a_wide_fallback_font and its guard: pass.
- Also pass: test_v2_nav_render, test_v2_writing_routes_render, test_v2_audit_render, test_waivers_render, test_v2_polish_render, test_launch_front_door, test_v2_finder_render, test_v2_find_split_render, test_v2_contract_render (6), test_v2_a11y_batch1_render, test_v2_phone_layout_render, test_v2_phone_landscape_render, and the guard cases of nav, writing routes, audit, polish, waivers.
- 1000 px wide: bar was 170 px (two rows) before, 64 px after (measured with Playwright, screenshots in the scratchpad: nav_before_*.png, nav_after_*.png).

### Test edits and why (layout definition changed, not loosened)
- test_v2_nav_render, test_v2_audit_render, test_waivers_render, test_v2_targets_render: tab list/order/labels are now the 14 menu entries; the short phone label ("Targets") no longer exists because phones use the same menu.
- test_v2_polish_render, test_launch_front_door: landing and unknown-hash route is the value chart (Jeremy, 2026-10-25), not Trade targets. Front-door tab click now goes to Trade targets through the menu.
- test_v2_overrides_basis_render: opens the menu before clicking the Overrides entry (3 places).
- test_v2_contract_render: RS-01 now expects Methodology, Research, Manifesto as Writing entries; scenario_tabs starts on #trade-targets (an empty hash is now the value chart); brand-link mutation anchor follows the brand link (#player-values).
- test_v2_phone_tap_targets_render: opens the menu only below 768 px (wider screens get a floating panel that would cover the controls being swept).
- test_v2_waterfall_render (wide-font check): it measured the tab row squeezing at 1024/1279 px. That row no longer exists, so it now checks the bar stays one row, the freshness button stays on screen and nothing scrolls sideways with the menu open, in DejaVu Sans; its guard mutation is now "menu opens in the bar".
- test_v2_hamburger_nav_render: wide screens now show the button; the "toggle leaks onto desktop" mutation is replaced by "menu leaks open on desktop".

### Claimed, not confirmed
- test_v2_targets_render (1366x768 "sell top 5 ends below the fold"), test_v2_overrides_basis_render (3 failures), test_v2_ux_render (hit areas at 820 px), test_v2_phone_tap_targets_render and test_v2_mobile_phase1_render fail identically on #944 before this change (run on the base: same first messages); not caused by this branch and not fixed here.
- test_v2_phone_fallback_font_render cannot run on this machine (DejaVu Sans missing); it reads `#v2NavToggle` and `.v2-tabs` and was not run.
- make test-core (run with -k): only tests.test_render_sweep_coverage failed (new test not wired); fixed by adding it to the Makefile run list and re-running that test (4 pass). The other test-core entries were OK; the full target was not re-run after the fix.
- Dark mode and the menu on a real touch phone were not looked at by eye; only 390 px headless.
