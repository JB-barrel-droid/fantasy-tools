## 2026-10-19 - JEG-477 chart taller on large screens, plus a taller/shorter toggle

- Decision (Jeremy, 2026-10-19): chart taller by default on larger screens (scales with viewport) plus an expand/contract toggle; laptop (JEG-470 fold) unchanged.
- Change: `app/v2/v2.css` adds `@media (min-width: 1680px) and (min-height: 960px)` with `--v2-chart-h: clamp(420px, calc(100vh - 530px), 60vh)` and `--v2-chart-h-expanded`; `#v2Main[data-chart-size="tall"]` applies it at any width. `app/v2/shell.html` adds `#v2ChartSize` (aria-pressed, label flips) in the zoom group; `app/v2/v2.js` toggles `data-chart-size` and calls `renderCharts()`. No value math touched.
- Measured plot height: 1440x900 378 px and 1366x768 280 px (unchanged, card ends 900 / unchanged); 1920x1080 454 -> 550 (page above the plot is 530 px, so the card ends at 1076, inside the fold); 2560x1440 scales further.
- Verified: tests/test_v2_chart_height_render.py (laptop heights pinned, large-screen heights, toggle expand/contract and svg redraw; 4 broken-build mutations all caught); tests.test_build_v2_page, tests.test_v2_expand_render pass; screenshots at 1440x900 and 1920x1080 inspected.
- Flaky, not caused by this change: tests.test_v2_chart_fit_render failed once with and once without the change (different assertions), passed on rerun with the change.
- Not run: make validate, 12-combo sweep (values untouched). Toggle button sits in the existing top-right zoom group and overlaps the STARTERS label as the other buttons already do.
