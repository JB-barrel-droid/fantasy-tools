## 2026-10-23 - JEG-957 Writing tab: sub-tabs stay above all sections

Cause: in app/v2/shell.html the Writing sub-tab row (#v2Writing) sat after the league bar (#v2League,
"Chart settings") and the sources bar (#v2Methods, "On the chart"). Those two are hidden for Manifesto and
Research but shown for How values work, so only that sub-tab rendered the tabs below them. v2.js does not move
the element. Fix: moved the #v2Writing block to directly after the header in shell.html (markup only).

Verified:
- Reproduced headless on a built dist: before, how-values at 1440 and 390 had v2League and v2Methods above the row.
- New tests/test_v2_writing_subtabs_order_render.py passes (3 sub-tabs x 1440/390); its
  test_guard_fails_on_broken_order serves the old order and requires the how-values failure.
- #v2How text length and section/li count identical before and after (3549/25 at 1440, 3515/25 at 390).
- Screenshots in ~/code/fantasy-tools-selfhost-notes/jeg-957/.

Claimed, not checked: other render test files (not run, per one-at-a-time rule); no v2.css change.
