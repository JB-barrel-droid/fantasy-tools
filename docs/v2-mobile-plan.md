# v2 Mobile Optimization Plan

Audit date: 2026-10-22. Screenshots in `~/code/fantasy-tools-selfhost-notes/mobile-audit/`.
Viewports tested: 390x844 (iPhone 14/15), 360x740 (older Android), 320x568 (iPhone SE), 844x390 (landscape).
Touch emulation enabled on all viewports with deviceScaleFactor 2.

---

## 1. Per-tab defect catalogue

### 1.1 Global / navigation

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| Nav tabs overflow at 320px: "Research" clipped off-screen | High | `320x568/player-values-viewport.png` |
| Nav tabs are a grid of 7 items in one row; at 390px they fit but are cramped (font-size 12px, no truncation labels used) | Medium | `390x844/manifesto-viewport.png` |
| Sticky topbar (brand + status + nav) consumes ~195px of vertical space on first viewport paint | Medium | all viewport screenshots |
| League settings bar (scoring, roster, Edit league, Position weights, source legend, Customize) repeats on every tab, consuming another ~280px before any tab content | Medium | `390x844/player-values-viewport.png` |
| 58 CSS `:hover` rules with no `@media (hover: hover)` guard and no `:focus-visible` fallback; hover-highlighted rows and buttons are invisible on touch devices | High | audit.json `hoverRules` |
| No `overscroll-behavior` set on the body or scrollable containers -- pull-to-refresh and scroll-chaining can interfere with in-page scroll regions | Low | code audit |
| Info popovers use `position: fixed` with JS-calculated coords; at 320px they can be clipped by small viewports when content is long | Medium | code audit (v2.js line 1283) |

### 1.2 Manifesto tab

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| No mobile-specific issues. Long-form text reads well. | -- | `390x844/manifesto-viewport.png` |

### 1.3 Player values tab (Trade targets)

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| **Table overflows viewport by 159-399px** at 390px; no horizontal scroll container; columns are simply clipped | Critical | `390x844/player-values-table.png`, audit.json `overflowEls` |
| Table header buttons (column sort toggles) are 22-32px tall, well below 44px minimum | High | audit.json `tapIssues` |
| Source link arrows ("↗") are 15x14px -- nearly impossible to tap | High | audit.json `tapIssues` |
| Column header text at 10-11px font size; sub-labels hidden on small screens | Medium | audit.json `smallText` |
| "Wk 6" badges at 11px with ~30px tap target | Medium | audit.json |
| "Columns" and "Expand" buttons at 30px height | Medium | audit.json |
| No sticky first column -- player names scroll out of view | High | `390x844/player-values-table.png` |
| Compare-methods view squeezes 6 columns into 390px with 4px gaps | High | CSS line 1333 |

### 1.4 Trade targets tab

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| Main table (`v2-wtable`) overflows by 399px at 390px | Critical | audit.json `overflowEls` |
| Expand buttons (`v2-texpand`) overflow by 387px | Critical | audit.json |
| Source links in legend are 17px tall (height), below 44px touch target | High | audit.json `tapIssues` |
| Signal badges and delta chips at 11px font | Medium | audit.json `smallText` |
| The chart (SVG in `.chart-shell`) uses `mousemove`/`mouseleave` only for hover-inspect; no touch-move handler means mobile users cannot scrub the chart to see values | Critical | v2.js lines 1264-1271 |
| Chart tooltip positioning uses mouse coordinates; no large-crosshair or offset logic for finger obstruction | High | v2.js |
| Drawer (player detail overlay) positioning may clip at bottom on short viewports | Medium | code audit |

### 1.5 Risers & fallers tab

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| Movement table grid at 620px breakpoint uses `minmax(0,1fr) 52px 52px 58px` -- adequate at 390px but cramped at 320px | Medium | `320x568/risers-fallers-viewport.png` |
| Movement graph sub-tab (SVG canvas) has no touch-to-inspect; relies on hover | High | code audit |
| "All players" sub-tab table shares the same overflow issues as Player values | High | code audit |
| Source tabs (pill buttons) at 11px font with small touch targets | Medium | code audit |

### 1.6 Compare a trade tab

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| Player search inputs are 36px tall (below 44px) | Medium | audit.json `tapIssues` |
| "Show players" buttons are 24px tall | High | audit.json |
| Source links in per-source breakdown are 17px tall | High | audit.json |
| Checkboxes (roster checkboxes) are 20x20px | Medium | audit.json |
| Trade grid collapses to single column at 900px which works, but "You give" / "You get" side labels have no visual separator on single-column layout | Low | `390x844/compare-trade-viewport.png` |
| "Find a trade" roster import inputs may overflow on small screens | Medium | `390x844/compare-trade-full.png` |

### 1.7 How values work tab

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| View-mode tabs (Indexed/VORP/Adjusted) at 13px font, adequate but cramped | Low | `390x844/how-values-viewport.png` |
| Methodology tabs (3-column grid) drop subtitles at 620px -- good | -- | CSS line 1262 |
| Recalibration table (`recal-table`) has `max-height: 420px` scroll container with sticky thead, but the table can still overflow horizontally | Medium | code audit (CSS line 239-248) |

### 1.8 Research tab

| Defect | Severity | Screenshot ref |
|--------|----------|---------------|
| No content ("No posts are published yet") -- no mobile issues yet | -- | `390x844/research-viewport.png` |

---

## 2. Chart interaction on mobile: problems and recommended patterns

### Current state
- The main value chart (SVG in `.chart-shell`) uses `mousemove` for hover-to-inspect and `click` to open a player drawer. On touch devices, users can tap to open a drawer but **cannot scrub across the chart to see values** -- the primary desktop interaction is completely missing.
- The curve widget canvas (`#curve-widget #chart`) correctly handles touch via `touchstart`/`touchmove`/`touchend` with `touch-action: none`. This is the right pattern; the main chart should follow it.
- The chart is rendered at full width within a container that bleeds to screen edges at 620px breakpoint (negative margins), which is correct.

### Research: best practices for dense data charts on mobile

**Sources consulted:**

- [Boundev.ai: Mobile Data Visualization Design Guide](https://www.boundev.ai/blog/mobile-data-visualization-design-guide) -- tap replaces hover; two-finger zoom; thumb zone placement; prevent scroll hijacking
- [Material Design 3: Touch targets](https://m3.material.io/foundations/accessible-design/interaction) -- 48dp minimum touch targets
- [Apple HIG: Layout](https://developer.apple.com/design/human-interface-guidelines/layout) -- 44pt minimum touch targets, safe area insets
- [Datawrapper mobile charts](https://blog.datawrapper.de/mobile-data-visualization/) -- tap-to-inspect, large crosshair with label offset
- [Smashing Magazine: Responsive Tables](https://smashingmagazine.com/2022/12/accessible-front-end-patterns-responsive-tables-part1) -- sticky first column + horizontal scroll
- [Can I Use: Screen Orientation API](https://caniuse.com/mdn-api_screenorientation) -- iOS Safari limitations on lock/unlock

**Recommended patterns:**

1. **Tap-to-inspect with offset label.** On touch devices, `touchstart`/`touchmove` on the chart surface should show a crosshair + value label positioned *above* the touch point (offset by ~60px so the finger does not obscure it). Lifting the finger (touchend) should keep the last-inspected value visible for 2 seconds, then fade. Tapping a data point opens the player drawer (existing click behavior).

2. **Two-finger pan/zoom vs. full-screen pop-out.** Two-finger zoom on an inline chart conflicts with page zoom and scroll. A dedicated full-screen chart pop-out is safer and gives the chart the full viewport.

3. **Chart full-screen pop-out design:**
   - Trigger: a prominent "expand" button on the chart (already exists: `⤢ Expand`), plus an explicit "View full screen" touch target at 44px+ height.
   - Opens a full-viewport overlay (`position: fixed; inset: 0`), dark background, chart fills the available space minus a top bar with close button and position filter.
   - **Landscape handling (DECISION NEEDED -- see Section 4, Decision A).**
   - Controls: position filter pills at top; close button (44px+) top-right; value label anchored to top bar, not floating.
   - Dismiss: close button, swipe-down gesture, or back button / Escape.
   - `touch-action: none` on the chart container to prevent scroll-chaining.

4. **Large touch crosshair.** A vertical line + horizontal line (full chart height/width, 1px, 30% opacity) plus a filled dot (8px radius) at the data point, with the value label in a chip anchored to the top of the chart area (not following the finger). This avoids finger-over-data occlusion.

---

## 3. Table and layout recommendations

### Tables (Player values, Trade targets, Risers all-players)

**Pattern: sticky first column + horizontal scroll container.**

Wrap the table in a `div` with `overflow-x: auto; -webkit-overflow-scrolling: touch`. Apply `position: sticky; left: 0; z-index: 2; background: var(--paper)` to the first column (player name). Add a subtle drop shadow on the right edge of the sticky column to indicate scrollability.

At `max-width: 620px`, consider:
- Hiding lower-priority columns by default (source links, badges) behind a "Columns" selector
- Showing only player name, DDF Value, and one comparison column; other columns available by horizontal scroll
- Increasing row height to 48px minimum for touch targets
- Using `scroll-snap-type: x mandatory` on columns to prevent partial-column views

**Alternative (DECISION NEEDED -- see Section 4, Decision B):** card layout instead of table rows on mobile.

### Navigation tabs

At `max-width: 400px`, switch from 7-column grid to horizontal scroll strip with `overflow-x: auto; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch`. Each tab gets `scroll-snap-align: start`. Active tab scrolls into view. Alternatively, collapse to a hamburger or bottom-sheet nav.

**Recommended:** horizontal scroll strip with scroll-snap (simplest, preserves all tabs visible, familiar pattern from iOS tab bars and Material top tabs).

### League settings bar

The league settings block (scoring, roster, buttons, source legend, Customize) occupies ~280px at the top of every data tab. On mobile this pushes the actual content below the fold.

**Recommended:** Collapse to a single-line summary ("Full PPR · 12 teams · 3 sources") with a tap-to-expand drawer or bottom sheet. The "Edit league" and "Customize" actions move into that drawer. Source legend becomes a collapsible section within the drawer.

### Dialogs and panels

The code already goes full-screen below 768px for panels (v2.js: "full screen below 768 px (frame 17)"). Verify this is working and that the full-screen panel has proper safe-area insets (`padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)`).

### Touch targets

All interactive elements need `min-height: 44px` (Apple HIG) or `min-height: 48px` (Material). Key fixes:
- Source link arrows: wrap in a 44px tap target area with padding
- Table header sort buttons: increase to 44px height
- "Show players" buttons: increase to 44px
- Checkboxes: use 44px touch wrapper
- Badge pills: either increase size or use touch padding (the badge itself can stay small if the tappable area extends via padding/margin)

### Small text

Minimum readable body text on mobile is 16px (WCAG); minimum for secondary text is 12px. Several elements use 9-11px (badges, sub-labels, footer items). Increase to 12px minimum.

---

## 4. Decisions for Jeremy (multiple choice)

### Decision A: Chart full-screen landscape handling

When the user opens the chart full-screen on a phone in portrait, should the app:

**(A1) Show a "rotate for best view" prompt.** The chart opens full-screen in the current orientation. A one-time hint overlay says "Rotate your phone for the best chart view" with a rotate-phone icon. If the user rotates, the chart reflows to landscape dimensions automatically (CSS/JS reflow). No orientation lock (not supported on iOS Safari).
- Pro: No platform limitations; works everywhere; respects user choice.
- Con: Chart may be too short in portrait full-screen (390px wide, ~300px chart height after controls).

**(A2) Auto-rotate the chart content.** The chart renders rotated 90 degrees via CSS `transform: rotate(90deg)` inside the full-screen overlay, so the chart is always in landscape layout regardless of phone orientation. Close button and labels rotate too.
- Pro: Chart always gets full use of the longest dimension.
- Con: Disorienting UX; phone status bar and OS controls stay in portrait; text reads sideways if user does not physically rotate.

**(A3) Portrait-optimized chart.** Keep the chart in portrait orientation but re-layout the axes: player rank on the Y axis (vertical, scrollable), value on the X axis (horizontal). Effectively a horizontal bar chart in full-screen.
- Pro: No orientation dependency; works naturally in portrait; each bar is a tap target.
- Con: Loses the familiar multi-series line/scatter chart appearance; significant rendering change.

**Recommendation:** A1. A prompt is honest and non-disorienting; the chart works in portrait (just shorter), and landscape gets the premium view. iOS Safari does not support `screen.orientation.lock()`, so A2 is the only real alternative, and it creates worse UX than a prompt.

### Decision B: Mobile table layout -- scroll table vs. card layout

For the Player values and Trade targets tables on screens under 620px:

**(B1) Sticky-column scroll table.** Keep the table; add a horizontal scroll container with sticky player-name column and shadow affordance. Hide low-priority columns behind a "Columns" selector. Rows stay at 48px+ height.
- Pro: Preserves quick-scan comparison across many players; sort still works naturally; minimal rendering change.
- Con: Horizontal scroll on a vertically scrolling page can be finicky; data density is still high.

**(B2) Card layout.** Each player becomes a card showing name, position, DDF Value, and a condensed multi-source comparison. Tap to expand for full details. Cards stack vertically.
- Pro: Touch-native; no horizontal scroll; each card is a clear tap target; progressive disclosure.
- Con: Loses at-a-glance comparison across players; scrolling through 100+ cards is slower than scanning a table; significant template rewrite.

**(B3) Hybrid.** Default to a 3-column table (rank, player, DDF Value) with sticky first column and horizontal scroll revealing additional columns. Long-press or chevron on a row expands an inline card showing all sources for that player.
- Pro: Best of both worlds; table for scanning, card for detail.
- Con: Two interaction patterns to learn; more complex implementation.

**Recommendation:** B1 (sticky scroll table). It matches the data-comparison purpose of the tool, preserves sorting, and is the industry standard for dense data tables on mobile (Datawrapper, Bloomberg, ESPN all use this pattern). Cards work for e-commerce but not for comparative analytics.

### Decision C: Navigation pattern on mobile

**(C1) Horizontal scroll tabs.** Keep all 7 tabs visible in a single horizontally scrollable row. Active tab auto-scrolls into view. `overflow-x: auto` with `scroll-snap`.
- Pro: Simplest; all tabs discoverable; no extra tap to see hidden tabs.
- Con: Last 1-2 tabs may be off-screen; users must know to scroll.

**(C2) Collapsible hamburger menu.** Replace tabs with a hamburger icon that opens a full-screen or bottom-sheet menu listing all tabs.
- Pro: Saves vertical space; all tabs equally accessible.
- Con: Hides navigation; extra tap to switch tabs; breaks the "tab strip" mental model.

**(C3) Bottom tab bar (5 tabs) + "More" overflow.** Move navigation to a fixed bottom bar with the 5 most-used tabs and a "More" item for How and Research.
- Pro: Thumb-friendly (bottom of screen); persistent; standard mobile pattern.
- Con: Loses 44px of viewport to the persistent bar; more complex implementation; would need to distinguish from the existing top navigation.

**Recommendation:** C1. Horizontal scroll tabs are the lightest change, standard on mobile web (Material Design top tabs), and keep all navigation one tap away. The current 7-tab strip already nearly fits at 390px; it just needs `overflow-x: auto` and scroll-snap.

---

## 5. Proposed phased ticket breakdown

### Phase 1: Foundation -- touch targets, overflow, and scroll containers
**Scope:** Fix the most critical defects that make the app unusable on mobile.
**Files:** `app/trade-value-chart/v2/v2.css`, `dist/v2/index.html` (the CSS)
**Gate:** All interactive elements >= 44px touch target; no horizontal overflow at 390px; `make validate` green.

Tickets (each one code path):
1. **Nav tab horizontal scroll** -- add `overflow-x: auto` + scroll-snap to `.v2-tab-strip` at `max-width: 400px`
2. **Table scroll containers** -- wrap `.v2-table`, `.v2-wtable`, `.recal-table-wrap` in `overflow-x: auto` containers with sticky first column
3. **Touch targets pass** -- increase all interactive elements to 44px minimum (source links, table headers, buttons, checkboxes, badges)
4. **Small text pass** -- increase all text to 12px minimum on mobile
5. **Hover rule audit** -- wrap all hover-only styles in `@media (hover: hover)` or add `:focus-visible` fallbacks

### Phase 2: Chart mobile interaction
**Scope:** Make the chart usable on touch devices.
**Files:** `app/trade-value-chart/v2/v2.js` (chart interaction), `app/trade-value-chart/v2/v2.css`
**Gate:** Chart tap-to-inspect works on touch; crosshair visible; value label not obscured by finger.

Tickets:
6. **Chart touch-to-inspect** -- add `touchstart`/`touchmove` handlers to the main chart SVG, with offset crosshair and value label
7. **Chart full-screen pop-out** -- full-viewport overlay with close, position filter, landscape prompt (per Decision A)

### Phase 3: Layout optimization
**Scope:** Reduce vertical space waste and improve content density.
**Files:** `app/trade-value-chart/v2/v2.js`, `app/trade-value-chart/v2/v2.css`, `dist/v2/index.html`
**Gate:** First meaningful content visible within one viewport height on 390px.

Tickets:
8. **League settings collapse** -- single-line summary with tap-to-expand on mobile
9. **Topbar compaction** -- reduce brand + status bar height on mobile
10. **Table layout per Decision B** -- implement chosen table pattern (scroll table or cards)

### Phase 4: Polish and edge cases
**Scope:** Safe area insets, overscroll, landscape, dialog sizing.
**Files:** `app/trade-value-chart/v2/v2.css`, `app/trade-value-chart/v2/v2.js`
**Gate:** No visual issues at 320px-844px range; `make validate` green.

Tickets:
11. **Safe area and overscroll** -- add `env(safe-area-inset-*)` padding, `overscroll-behavior: contain` on scroll containers
12. **Dialog/panel mobile audit** -- verify full-screen panels at 320px, safe-area insets, close-button accessibility
13. **Compare-a-trade mobile** -- ensure trade inputs, roster panels, and result display work at 320px

---

## 6. Chart pop-out design (detailed)

### Trigger
- The existing "Expand" button on the chart shell, restyled to 44px minimum height with clear "Full screen" label on mobile.
- Alternative: double-tap on the chart surface (with a brief hint toast on first visit).

### Overlay structure
```
+----------------------------------------------+
| [X Close]   QB  RB  WR  TE  ALL    [i]       |  <- 44px top bar
|----------------------------------------------|
|                                              |
|              CHART SVG                       |  <- fills remaining viewport
|              (touch-action: none)            |
|                                              |
|----------------------------------------------|
| Player Name   Value: 45.2   Rank: #12       |  <- value readout bar, 44px
+----------------------------------------------+
```

### Landscape handling (per Decision A)
- Chart reflows to available dimensions via CSS (`width: 100vw; height: 100vh` on the overlay).
- On first open in portrait, a 3-second fade-out hint shows a rotate-phone icon and "Rotate for best view".
- Hint is shown once per session (stored in sessionStorage).
- No `screen.orientation.lock()` call (not supported on iOS Safari).

### Touch interaction in full-screen
- `touch-action: none` on the chart container.
- Single-finger horizontal drag scrubs across data points, showing crosshair + value in the readout bar.
- Single-finger vertical drag is ignored (no pan).
- Tap on a data point opens the player drawer (existing behavior), which slides up as a bottom sheet in full-screen mode.
- Two-finger pinch: not supported in v1 (chart has no zoom axis). Reserve for future.

### Close behavior
- Close button (X, 44px, top-right).
- Swipe down from top 60px of overlay dismisses.
- Hardware back button / `popstate` event closes overlay (push a history state on open).
- Escape key closes (existing keyboard handler).

### Fallbacks
- iOS Safari: no orientation lock; prompt-only. `screen.orientation` read events work for detecting landscape and reflowing.
- Older browsers without `position: fixed` support: chart opens in a new scroll position instead of overlay (progressive enhancement).
- Screen readers: overlay is `role="dialog"` with `aria-modal="true"`; focus trapped; close returns focus to the expand button.
