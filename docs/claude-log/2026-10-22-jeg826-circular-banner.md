## 2026-10-22 - JEG-826 interim honesty layer (circular blend banner)

PR: #789
Ticket: JEG-826 (Urgent)

### What changed

When DDF Value's blend is built entirely from trade charts (no projection
source is current), the site now shows:

- A yellow banner on Trade targets and Compare verdict: "This week, our value
  is built entirely from the same trade charts it is compared with. The gaps
  on this page reflect the rescaling, not an independent check. Projection
  sources are updating."
- Softened copy: "Offer them" / "Ask for them" becomes neutral; "Every source
  agrees" becomes "All sources point the same way ... but they share the same
  inputs"; deal read text gets a parenthetical noting shared inputs.
- An inline note on How values work's DDF Value definition.
- All banners auto-hide when independent sources return (computed from live
  data via `blendIndependenceCheck()`, not hardcoded).

### How "independent" is decided

`blendIndependenceCheck(ourKey)` in v2.js reads `composite.series` from the
engine (the sources actually contributing to the blend this week) and compares
against the chart key set (`usatoday`, `fantasycalc`, `fantasypros`, `cbs`).
Circular = every blend source is a chart AND fewer than 2 independent (non-chart)
inputs exist. When a projection source comes back, `composite.series` includes
it, `independent >= 1`, and the banners disappear on the next render.

### Files touched

- `app/v2/v2.js` — `blendIndependenceCheck()`, banner rendering in
  `renderTargets()`, `renderVerdict()`, `renderDeal()`, `renderHow()`,
  `verdictCopy()`, `renderStory()`; exposed on `window.TradeValueV2`.
- `app/v2/shell.html` — 3 banner/note elements (`v2TCircularBanner`,
  `v2CCircularBanner`, `v2HowCircular`).
- `app/v2/v2.css` — `.v2-circular-banner` styles with dark mode.
- `tests/test_v2_circular_banner_render.py` — 2 render tests covering both
  states (independent: no banner; circular: banner visible + softened copy).

### Verified

- `test_v2_circular_banner_render.py`: 2 passed
- `test_v2_targets_render.py`: 2 passed, 28 subtests passed
- `make validate`: passed (one transient `test_week_history` failure that
  passes in isolation, unrelated)

### Not verified

- Live page after deploy (PR not yet merged)
- 12-combo headless sweep (not required: no value math or chart changes)
