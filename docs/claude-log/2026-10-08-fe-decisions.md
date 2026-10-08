# 2026-10-08 · v2: build Jeremy's brand, landing and label decisions

## Verified

- All eleven `tests/test_v2_*_render` suites OK (with guards); `tests.test_launch_front_door`,
  `tests.test_live_page_synthetic`, `tests.test_static_export`, `tests.test_v2_targets` OK.
- Headless screenshots at 1440, 820 and 390: root opens on Trade targets under "Data Driven Football";
  plain labels at 1440 and 820, short forms at 390; no page errors, no overflow at 390.

## Fixed on the way

- `getHistoryWeeks` threw on the live site (it referenced `HISTORY_UNSUPPORTED`, removed upstream), so
  Risers & fallers offered only the current week pair. Caught by `test_v2_risers_render`.

## Test assertions changed, and why

- `tests/test_launch_front_door.py` (launch lane): v2 title is now "Data Driven Football" and the root
  lands on Trade targets, both by Jeremy's 2026-10-08 decision. Classic title assertion unchanged.
- `tests/test_v2_nav_render.py`: ESPN now has a prior week upstream, so "every Δ cell reads Δ —" no
  longer holds; the check is now "Δ — for every series the engine has no prior week for".
- `tests/test_v2_states_render.py`: mutation anchor follows the renamed matrix columns.
