# v2 design notes: build log (archived 2026-10-15)

Dated working sections moved out of `docs/v2-design-notes.md` (JEG-602): gap lists from the 2026-10-08 Figma review and the passes that closed them, page-weight measurements, and the multi-device sweep. Not maintained; the live behavior is in the remaining notes, `docs/feature-contract.md` and the tests. Nothing deleted.

## Figma review: what the frames specify that the build lacks (2026-10-08)

Every frame was read on the canvas. The frames use illustrative Week 4 numbers, the old brand
("Trade Value") and the old tab name "Market disagreement"; those are not gaps (brand rule, and
Jeremy's Trade targets decision). "VORP" alone and "Pure VORP" in the frames become "VORP vs
waivers" (copy rule).

- **05 / 06 Risers & fallers.** Title "Risers & fallers." / "Value-point changes. One source. Two
  snapshots." Risers and Fallers are two cards side by side at 1440 (stacked at 390), not one
  table behind a toggle. Each row: name, "Pos · Team", "before → after", ▲/▼ signed Δ, and a bar on
  one shared scale ("Bars share a scale of N value points"). Controls: "Movement: <source>" and a
  week-pair picker "Week 3 → Week 4" (frame 19 #05: only this tab has the N−1 → N control). Methods
  row visible. Footnote "Δ — for missing history · Never a zero change." Build: table with
  Week N / Week N−1 columns, Risers/Fallers toggle, no bars, no week-pair picker, Methods row hidden.
- **07 / 08 Compare a trade.** Title "Build a better offer." / "See the deal through every selected
  source." "Player values shown: <series>" puts that series' value next to every player on both
  sides and a "<series> total" at the foot of each side. "You give" / "You receive". "Swap sides ⇄"
  and "Clear trade". A story callout ("Same publisher. Different result.") when one publisher's
  DDA and Indexed nets have opposite signs (frame 22 #15: complete comparable rows only, names the
  publisher, methods and signed nets from data; no conflict = summarize agreement; different weeks =
  no contrast story). "Difference by source & method" rows: source, Give, Receive, a diverging bar
  (Less value | More value) and the signed net; a row expands to player-by-player arithmetic
  (frame 24 "Expanded result"). Mobile: rows become cards ("98.0 give → 94.0 receive", bar, net);
  Swap / Clear at the foot. Build: no per-player values, no side totals, no swap, no story, no
  bars, no expansion; a missing value reads — instead of "Incomplete" (frame 18).
- **13 / 14 Player detail.** × close (44 px). Hero card: ranking series, big value, "Trade-value
  points", and the active source range. "Source values" matrix: one row per publisher with week,
  columns Adjusted / Indexed / VORP; cells show the value, "Available ↗" (not selected, adds it),
  "Not selected", "Older" or —. "Stats & context", "Latest player news", "Adjustments applied",
  then "See market disagreement" and "Add to trade" (a menu chooses Give or Get). Source rows open
  provenance. Mobile 14 is full screen, not a bottom sheet; the matrix scrolls sideways. Build:
  lists grouped by method, "Close" text button, no hero, no news, two separate add buttons,
  bottom sheet on mobile.
- **15 / 16 How values work.** Title "Know what the numbers mean." / "Three methods. Visible source
  context. Your league settings." (mobile "Know your values." / "Three methods. One clear
  comparison."). Methods row visible. Cards in the order DDA, Indexed ("Source-relative index"),
  VORP, each with a method pill and two short lines. "Your league shapes the comparison": league
  line, position weights, bench allocation, and a Weights & bench button. "Read the evidence, then
  make the call." Build: VORP first, long copy, no weights/bench line, Methods row hidden.
- **18 States.** Loading keeps league and source controls visible with a skeleton chart and rows.
  "No current-week sources" offers [Choose older sources] [Retry]. "No player matches" offers
  [Clear search] [Reset position] separately. "Only one comparable series" offers [Choose sources].
  "Partial source failure": other series stay, warning badge, [Retry source] in freshness.
  "Incomplete trade": that source's total and difference read "Incomplete" and name the missing
  player. "No sources / incompatible league": keep the last series and say "Choose at least one";
  when a league change drops a pair, say which. "Empty trade": "Search and add a player" per side;
  players selected on one side are disabled on the other. "Stale source explicitly selected":
  freshness offers [Remove older source]. Build: loading hides every control, one Clear filters,
  no dropped-pair notice, no remove-older action, chosen players vanish from search instead of
  showing "Added".
- **20 Source selection, mobile (same layout as 09 at 720 wide).** "Choose your sources": a
  "N pairs selected" summary, one block per publisher (kind + week) with a toggle per supported
  method ("✓ DDA", "+ VORP", "+ Indexed"), older-week publishers disabled until "Include Week N"
  is on, "Only supported pairs are offered. VORP stays in its own panel.", Cancel / "Apply N
  pairs" (a draft, applied at once). Full screen below 768. Build: method-grouped checkboxes that
  apply on every click, a popover on every width.
- **21 Chart options.** Opened from "Chart options" in the chart header (mobile: "···"). Player
  range Full / Top 25 / Top 50 / Starter / Bench / Waiver (presets follow the ranking series;
  Starter / Bench / Waiver use the league's roster boundaries), "Hide zero-value tail", Y axis
  Auto / Custom bounds (lower, upper), table metadata columns Position / Team / Tier, Cancel /
  "Apply chart options". Build: All / Top 100 / 50 / 25 buttons only.
- **23 Benchmark decisions.** A rationale frame, no screen. Adopted: source-specific mover lists, a
  clear week basis, always-available search; compact data-first controls; min/max value filter
  without buy/sell verdicts; totals and signed bars per pair without a fairness label; a rank-range
  navigator with numeric bounds, keyboard control and reset.
- **24 Navigator, filters & trade detail.** Rank navigator: overview line of the ranking series
  under two handles, "From N" / "To N" number fields, "Reset to all"; Left/Right moves a bound one
  rank, Home/End jump. Value range: "Basis <series> · Week N", "Keep players with values between",
  Minimum / Maximum plus a two-handle slider, "Missing values are excluded with a visible count",
  Clear range / Apply. Trade search: results show position, team and value; an already chosen
  player shows "✓ Added"; no results keeps the query and offers Clear search. Build: no overview
  line or number fields in the navigator, no basis week or slider in the range filter.
- **09 – 12 overlays** (mapped earlier, not re-checked until now). 09 = frame 20 layout. 10 "Source
  freshness": an earlier-week banner, a Source / Snapshot / Status table that includes
  unavailable sources, "Manage selected sources". 11: titled panel with ×, bench share slider with
  "Starters N% / Bench N%", position shares, Reset defaults / Cancel / Apply. 12 "Your league":
  segmented scoring and team buttons, steppers per roster slot including SUPERFLEX, Reset defaults
  / Cancel / Apply. Build: small popovers that apply on change; no SUPERFLEX.
- **Mobile navigation (02/04/06/08/16).** Below 768 the tabs are short labels on one row (Values ·
  Split · Movers · Trade · More). Build: full labels wrapping onto extra rows.

## Aligned with the frames (2026-10-08, task 2)

- **Risers & fallers (05/06).** "Risers & fallers." title. Risers and Fallers are two cards side by side
  (stacked below 768). Each row: name, Pos · Team, "before → after", ▲/▼ signed Δ and a bar; both cards
  share one bar scale, named under the cards. "Movement: <series>" plus a week-pair picker
  ("Week N−1 → Week N", latest first). The served pair is the engine's rows minus `getPriorWeek`; an
  earlier pair is `getWeekValues(series, N) − getWeekValues(series, N−1)`, both at the reader's league.
  The saved weeks come from a new read-only accessor `TradeValueCurveControls.getHistoryWeeks(series)`
  → `{servedWeek, weeks[]}`. Deviation: the Methods row and the Player values filters (value range,
  rank by, Δ toggle) shown in frame 05 stay off this tab; they change nothing here.
- **Compare a trade (07/08/24).** "Build a better offer." "Player values shown" (one exact series,
  ranking series by default) puts each player's value on both sides and a "<series> total" under each
  (`TradeValueTrade.sideTotal`: incomplete, never 0, if any player lacks the value). "You receive". Swap
  sides and Clear trade. Story card (`TradeValueTrade.tradeStory`): "Same publisher. Different result."
  when one publisher's DDA and Indexed nets flip sign in the same week; otherwise "every complete source
  points the same way" or "the sources split", from complete rows only. Table "Difference by source &
  method": Give, Receive, a diverging bar (complete rows only, one scale per table), Receive − give.
  "Show players" opens the per-player arithmetic (frame 24). Search lists position, team and the
  ranking series' value; a chosen player stays listed as "✓ Added" / "✓ On You give", disabled; no
  match keeps the query and offers Clear search.
- **Player detail (13/14).** ✕ close. Hero: the ranking series' value with its week, plus the range
  across the selected Data Driven Adjustments series (same unit, frame 03's DDA-only rule). "Source
  values" matrix: one row per publisher and week, columns Adjusted / Indexed / VORP vs waivers; a cell
  is the value, — with a reason, or "Available ↗" / "Older ↗" for a series that is not selected (adds
  it). Stats & context; Latest player news and Adjustments applied from
  `TradeValueProductData.getPlayerContext` (read only); "See trade targets" and "Add to trade" (menu:
  You give / You receive). Full screen below 768.
- **How values work (15/16).** Frame titles (short ones below 768). Methods row shown. Cards in the
  order DDA, Indexed ("Source-relative index"), VORP vs waivers, with method pills. "Your league shapes
  the comparison" adds position weights (`getPositionWeights`) and bench allocation (`getBenchShare`)
  and a Weights & bench button. "Read the evidence, then make the call."
- **States (18).** Loading shows a skeleton chart and rows under the loading card. No player matches:
  one button per active filter (Clear search, Clear value range, Reset position; Clear all filters when
  two or more). Player values notice for "only one series selected" and "no current-week series
  selected", with Choose sources. A league change that drops a selected series says which one (status
  toast). Empty trade: "Search and add a player." per side.
- **Mobile navigation.** Below 768 the five tabs sit on one row with short labels (Values · Targets ·
  Movers · Trade · How); frames say "Split" and "More", renamed for Trade targets and How values work.

## Rails for the remaining screens (2026-10-08, task 3)

- **Choose your sources (09 / 20).** One block per publisher (kind, week, older weeks in amber) with a
  toggle per supported method: "✓ DDA" / "+ Indexed" / "+ VORP vs waivers". It is a draft: nothing
  reaches the engine until "Apply N pairs" (adds first, then removes, so the engine never hits zero).
  An empty draft is refused with "Choose at least one". Older-week pairs stay disabled until "Include
  Week N" is ticked; unavailable pairs are disabled with the engine's reason.
- **Source freshness (10).** Earlier-week banner; one row per engine series: snapshot week, provenance
  (freshness label, waiver note, publish date), status Current / Older · selected / Older · not
  selected / Unavailable. An active older series offers "Remove older source". "Manage selected
  sources" opens 09. The header badge shows ⚠ when a selected series is unavailable (frame 18
  "partial source failure").
- **Weights & bench (11).** Bench share slider as a draft with "Starters N% / Bench N%", feasible range
  from `getBenchBounds`, Reset defaults (15%) / Cancel / Apply. Position shares are shown read only
  from `getPositionWeights` (BE-2).
- **Your league (12).** Segmented scoring and teams, steppers for QB / RB / WR / TE / FLEX / Bench, as a
  draft; Apply goes through the dropped-series notice. "Reset defaults" returns to the engine's state
  at first load. No SUPERFLEX row (BE-2).
- **Chart options (21).** From the chart header ("Chart options", "···" below 768). Player range Full /
  Top 100 / Top 50 / Top 25 / Starter / Bench / Waiver; the last three are the engine's roster
  boundaries (`getZones`) mapped onto the filtered list. Hide zero-value tail, Y axis Auto / Custom
  bounds, Position / Team / Tier columns. Cancel / "Apply chart options".
- **Navigator and value range (24).** The brush track carries an overview line of the ranking series;
  "From" / "To" number fields and "Reset to all" sit under it (the handles keep arrow / Home / End).
  Value range names its basis series and week, has two handles mirroring Minimum / Maximum, refuses
  minimum above maximum, and still counts the players it leaves out.
- **Benchmark decisions (23).** A rationale frame with no screen of its own; its adopted items are the
  ones above and in task 2 (mover lists per source with a clear week basis, min/max filter, totals and
  signed bars per pair with no fairness label, navigator with numeric bounds and reset).
- All overlays are centered panels over a scrim on desktop and full screen below 768; Escape and the
  scrim close them; focus returns to the control that opened them.

## UX pass 2 (2026-10-08, task 5)

Swept every tab in light and dark at 1440, 820 and 390, with a computed-contrast check of every visible
text node (`tests/test_v2_a11y_render.py`).

- Contrast: green text on the pale green tint was 4.47:1 (light) and 4.4:1 (dark); it now uses
  `--v2-action-strong` (4.5:1+). In dark mode, white on the action green was 3.1:1; buttons on the
  action colour now use dark ink. Publisher symbols and chart lines were 2.1–3.4:1 on dark surfaces;
  dark mode now uses a lightened palette of the same hues (`DARK_COLORS` in v2.js), redrawn when the
  system theme changes. Hard-coded light tints (rank field border, active chip border, brush fill) are
  tokens with dark values.
- Keyboard: "Skip to content" is the first tab stop; it focuses the visible tab's main region (a button,
  because a #fragment would change the hash route). With player detail or a settings panel open, Tab and
  Shift+Tab stay inside it.

## Page weight (2026-10-08, JEG-449)

Measured on a local `make sync` build, headless Chromium, CPU slowed 4×:

| | Before | After |
| --- | --- | --- |
| Decoded bytes on first load | 8.8 MB | 4.1 MB |
| Time to usable, 390 px (Trade targets cards) | 7.0–10.7 s | 2.8 s |
| Time to usable, 1440 px | — | 2.5 s |
| `comparison-sources-data.json` downloads | 3 × 2.3 MB | 1 × 2.3 MB (261 KB gzipped) |

- The hidden engine container was `visibility: hidden` off-screen, which still lays out its 16,700
  nodes (about 3.2 s of layout and 1.1 s of style at 4×). It is now `display: none`. Proof that no
  number moves: `getAllRows()` (every series), `getSourceInfo()`, `getZones()`, weights, selection and
  every `TradeValueCurveDiagnostics` field are identical with and without it at four league settings
  (checked by hand), and `tests/test_v2_weight_render.py` repeats the row / info / zone comparison.
- A small script in the v2 head shares one network request per same-origin `.json` URL between the
  engine scripts (each caller gets its own clone; a caller's abort signal still rejects that caller).
- The classic page's fonts (Archivo, IBM Plex Mono) are no longer requested by v2.
- Not changed (back-end lane): the 1 MB inline `players-data` island (129 KB gzipped) and the 2.3 MB
  comparison file itself.

## League panel follow-ups (2026-10-08, JEG-442 / JEG-444)

- SUPERFLEX stepper (0–1) in Your league, on the engine's own `SUPERFLEX` roster slot (added by the
  superflex merge); the roster line names it when it is set. BE-2 now asks only for a position-share
  setter (JEG-452).
- A league change that moves the bench share says so ("Bench share moved from X% to Y% …"). Today the
  engine's feasible range is 1–30% at every roster, so this does not fire with real settings; the test
  simulates a re-clamp.

## Multi-device pass (2026-10-08)

Swept every tab at 390, 768, 820, 1024 and 1440 in light and dark (`tests/test_v2_ux_render.py`).

- Tablet (768–1023): the tabs were off screen past "Trade targets"; they now sit on their own row.
  The Methods row's source chips were squeezed into a one-chip column; they now take a full row.
- 44 × 44 hit areas (frame 17): tabs, zoom −/+, rank-window buttons and the brand link were 32–40 px.
  Chips and sort headers keep their compact look with an invisible 44 px hit box; chip rows have
  12 px between rows so neighbouring hit boxes do not overlap.
- Dark mode: hovered table rows, the status toast and the "Indexed" chip used light-only colours (a
  hovered row went near-white under light text). They now use tokens with dark values.

