# JEG-1263: Simplified site nav and route (2026-10-30)

Wires the Simplified site section (already on main from #1117/#1118) into the dashboard, per the hunk proposed on JEG-1263 (16:29 UTC 2026-10-29) and acked by the shell/design owner (03:03 UTC 2026-10-30).

- `shell.html`: nav group "Simplified site" inside `#v2Tabs` right after the Trade group (not in the Fieldnotes phone bar), plus `<main id="v2Simplified">`.
- `v2.js`: `viewFor`, `VIEW_TITLES`, `applyRoute` (and its `noShowing` list), the hide-all list and `refresh()`; one line each.
- `build_v2_page.py`: stylesheet and script includes after `opportunities.js`, and the copy list.
- `Makefile` and `v2-render-test.yml`: the two JEG-1263 test modules.

The section still withholds its answer until `TradeValueSimplifiedGates` is set by JEG-1259, JEG-1260 and JEG-1249. No value math, no league.js change.
