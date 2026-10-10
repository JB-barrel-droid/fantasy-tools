# v2 front end: design source and build notes

Figma file: https://www.figma.com/design/fCffo4EdZgUBkoVb7cQdr3/Trade-Dashboard-v2---Design-Review
(page "V3 · Resolved design & handoff"). The file opens without signing in. The Figma connector is
on the Starter plan and runs out of calls quickly, so these notes record what was read from the
canvas on 2026-10-07.

## Frame map (open with `?node-id=<id>`)

All 25 frames on the page, read in a browser on 2026-10-08 (node ids from the layers panel).

| Frame | Node |
| --- | --- |
| 00 Start here | 59-2938 |
| 01 Player values, desktop 1440 | 59-2077 |
| 02 Player values, mobile 390 | 59-2443 |
| 03 Market disagreement, desktop 1440 | 59-1817 |
| 04 Market disagreement, mobile 390 | 59-2567 |
| 05 Risers & fallers, desktop 1440 | 59-1956 |
| 06 Risers & fallers, mobile 390 | 59-2684 |
| 07 Compare a trade, desktop 1440 | 54-433 |
| 08 Compare a trade, mobile 390 | 59-2773 |
| 09 Source selection overlay | 54-957 |
| 10 Freshness overlay | 54-1028 |
| 11 Weights & bench overlay | 54-1128 |
| 12 League settings overlay | 54-1173 |
| 13 Player detail, desktop drawer | 59-2259 |
| 14 Player detail, mobile full screen | 59-1297 |
| 15 How values work, desktop 1440 | 59-2316 |
| 16 How values work, mobile 390 | 59-2862 |
| 17 Design system & responsive rules | 59-1484 |
| 18 Empty, loading & failure states | 59-1668 |
| 19 Implementation contract & feedback traceability | 59-1575 |
| 20 Source selection, mobile full screen | 59-1771 |
| 21 Chart options, shared overlay | 59-2395 |
| 22 Review amendments: interactions & source logic | 61-1593 |
| 23 Benchmark decisions & adoption | 68-109 |
| 24 Navigator, filters & trade detail states | 68-147 |

## Design language (frame 17)

- Colors: canvas #F3F7F7, ink #142B25, muted #64736F, border #DEE5E2, action #087F5B,
  positive #E9F5EF, negative #B33F50, older #A56320.
- Inter. 34/28 page title, 20 card title, 14 body, 12 metadata. 8 px spacing steps, 12 px card
  radius, 8 px buttons, 1 px borders. Numbers align right; the rank-source column gets a pale tint.
- ESPN green, FantasyCalc blue, FantasyPros purple; colors stay stable. DDA solid, Indexed dashed,
  VORP dotted. Always a label and a symbol; color alone never explains state.
- Desktop 1440 with 48 px margins; mobile 390 with 16 px. Below 768 px: stack cards, shorten
  navigation, full-screen settings. Every action has a 44 × 44 px hit area.
- Selected = filled action or labeled check; unavailable = dash + reason.

## Rules (frame 22, October review)

- Hover/tap a player: the crosshair follows the player ID across every series. Desktop hover and
  keyboard; mobile tap pins a detail sheet.
- Value range is measured against one exact series (the rank series). Blank bound = open ended,
  inclusive, reject min > max. Players missing that series' value are excluded and counted.
- Names appear on the chart only when each player has at least 64 px.
- Raw VORP goes in its own labeled panel; never compute a spread or aggregate across unlike units.
- Δ = current value − prior-week value for that exact pair, recomputed with current league and
  weights. No match: "Δ —" plus a reason, never zero. Off by default. Never substitute a stale
  curve or history.
- Trade story: each row = sum(receive) − sum(give) for an exact pair. No blended score or
  universal win/lose verdict.
- First-use default: available current-week DDA sources only. Selections, rank series, league and
  weights persist across tabs.

## How the build works

`pipelines/build_v2_page.py` (run by `make sync`) turns the built `dist/index.html` into
`dist/v2/index.html`. The current chart engine keeps running off-screen inside
`#legacyEngine`, and `app/v2/v2.js` renders the new layout from
`TradeValueCurveControls.getRows()` and related read-only accessors. v2 does no value math, so
its numbers are the current page's numbers. Settings changes call the engine's own setters.

## Trade targets tab (frames 03 / 04)

Frame 03 is titled "Where the sources split" and has a "Largest disagreements" table: ranking series
tinted, one column per series, a "DDA spread" column (highest − lowest, DDA only, current week
only), and "FC Index remains a separate value column". Frame 04 stacks that table as cards: name
and tier, the spread on the right, a one-line run of values underneath.

Built as **Trade targets** (`v2/#trade-targets`), per Jeremy's product purpose: find trades other
managers will accept. Sell where a public chart pays more than we would, buy where it pays less.
It keeps the frame's layout (table on desktop, cards below 768 px), but the comparison is one exact
pair per column, not a spread across sources:

- Our value = one engine series, picked in "Our value": `ddf_value` (DDF Value, the default since
  JEG-455, 2026-10-08), or the projections `espn`, `cbsros` (CBS rest-of-season) and `razzball` as
  alternatives. A series unavailable at the current setting is listed disabled with its reason; if
  the picked one becomes unavailable the tab fails closed rather than swapping. The pick survives
  switching tabs and is remembered on this device (see "Trade targets: DDF Value as our value").
- Each published chart = the engine's Indexed series (`usatoday`, `fantasycalc`, `fantasypros`,
  `cbs`), which the engine puts on the same trade-value point scale. VORP vs waivers is never
  paired with anything.
- Gap = chart value − our value (`app/v2/targets.js`, the tab's only arithmetic). Sell list =
  players with a positive gap, largest first; buy list = negative, most negative first. The
  "Largest gap" column names the chart it came from.
- Missing chart value: "—" plus "not on chart", no gap. Players without our value are left out
  and counted. A chart value of 0.0 is real: it is at or below that chart's waiver line for the
  league. Such a cell shows "0.0 · waiver line" with no gap, and is never a buy (Jeremy,
  2026-10-07: "It's illogical that 0 value players would be on a buy list"). Buying also needs our
  value above 0, which holds automatically (ours > chart > 0). The ESPN tier column is not used
  to filter: it comes from a different roster model than the ESPN line (risk row
  V2-TIER-VS-ESPN-LEG).
- Methods row stays hidden on this tab.
- Charts compared: every available one (JEG-459, 2026-10-08; the "Include older-week charts" opt-in
  is gone). A chart that has not published the current week yet is compared on its latest week and
  carries a "Wk N" badge. Position is the engine's shared setting, so it carries across tabs.
- Fails closed if the picked series is unavailable, or if the engine is not in its Indexed view (where the
  published series would be in a different unit).

## Compare a trade tab (frames 07 / 08)

Built as **Compare a trade** (`v2/#compare-trade`) on 2026-10-08, first from the frame 22 rule, then
brought in line with frames 07/08/24 the same day (see "Aligned with the frames" below).

- Two cards, "You give" and "You get", each with a player search (all positions, from the engine's
  new read-only `TradeValueCurveControls.getAllRows()`, which ignores the position filter). Search
  results are ordered by the ranking series' value. A player can be on one side only.
- "The trade by each source": one row per selected, available series (ranking series first, then
  DDA, then Indexed). Columns: You give (sum), You get (sum), Get − give. Arithmetic is in
  `app/v2/trade.js`, the tab's only arithmetic: `net = sum(receive) − sum(give)` per series.
- No blended score, no overall verdict. Each net carries a label and a symbol for that source only:
  "▲ you get more by this source", "▼ you give more by this source", "= even by this source".
- A player with no value in a series: that row shows — in all three cells plus "No <source> value for
  <player>", never a 0. A real 0 (at the series' waiver line) counts as 0.
- VORP vs waivers series get their own card and table, never mixed into the trade-value table.
- The Methods row (source selection) is shown on this tab; the selection is shared across tabs. The
  sides are v2 module state, so they survive switching tabs (no storage, like the other v2 state).
- Below 768 px each source row stacks as a card: source name, then give / get / net with labels.

## How values work tab (frames 15 / 16)

Built as **How values work** (`v2/#how-values`) on 2026-10-08 from docs/methodology.md "The Three
Views", then brought in line with frames 15/16 (see "Aligned with the frames" below).

- No new numbers. The only numbers on the tab are the "Your league" line (engine `getState` and
  `getRosterShape`, the same text as the league bar) and the 1-2-3 step markers.
- Three cards, in the methodology's order: VORP vs waivers (dotted), Data Driven Adjustments
  (solid), Indexed (dashed). Each lists the engine's series of that method from `getSourceInfo()`,
  unavailable ones with a reason and older weeks labeled from the freshness record.
- "Reading the numbers": — means missing, 0 is at or below the waiver line, one source at a time,
  older weeks labeled, label + symbol. Links to the other tabs.
- The Methods row is hidden on this tab (nothing to select). Three columns at 1440, stacked below 768.

## Player detail and frame 18 states (frames 13 / 14 / 18)

Built 2026-10-08 from frame 22's "mobile tap pins a detail sheet", then brought in line with frames
13/14/18 (see "Aligned with the frames" below; the bottom sheet is now full screen).

- Player detail groups values by method: Data Driven Adjustments and Indexed (trade-value points),
  then VORP vs waivers (each source's own scale). A missing value reads "— not priced by this source".
  At 1440 it is the 440 px right-hand drawer; below 768 px it is a bottom sheet (full width, up to
  85% of the screen, rounded top, grab handle, Close top right).
- Loading: the page starts with every tab hidden behind a loading card ("Loading values for your
  league…"); the tabs appear once the engine has rows.
- Failure: if the engine reports an error or does not finish in 30 seconds, every tab and the Methods
  row stay hidden and a failure card says why, with "Try again" (reload). No value is shown.
- Empty: on Player values, filters that leave no player hide the chart and table and say which filter
  did it (search text, value range, position), with "Clear filters".
- Overlays 09–12 (sources, freshness, weights & bench, league) were already built; no change.

## Navigation, Δ prior week and detail → trade (2026-10-08)

- Below 768 px the tabs wrap onto extra rows instead of scrolling sideways, so every tab is on screen
  at 390 (they were cut off past "Risers & fallers"). In-build tabs keep their "soon" label.
- Δ prior week on: the reason is visible text under the filters, not only a hover title. Every Δ
  stays "Δ —" until the prior-week contract below exists.
- Player detail has "↑ Add to You give" / "↓ Add to You get". It puts the player on that side of
  Compare a trade and opens the tab; once on the trade, the detail says so and links to the tab. A
  player's name on Compare a trade opens the detail.

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

## Product decisions (Jeremy, 2026-10-08, task 4 review)

Asked as multiple choice after the product-marketing review. Brand, landing tab and labels were built
the same day (see below); the rest are decisions, not code.

- **Brand:** nav wordmark, `<title>` and og:title become "Data Driven Football".
- **Landing tab:** a first visit opens on Trade targets; shared trade links still open Compare a trade.
- **Chips and legends:** plain names at 768 px and up ("ESPN · Our value · Week 5", "FantasyCalc chart ·
  Week 5", "Solid = our value · Dashed = published chart"); the short forms only below 768.
- **Publisher-data rights:** the first release is a proof of concept without legal concerns; rights are
  the next step once it works.
- **Trade verdict:** keep none; per-source rows plus the story card.
- **Page weight:** fix (about 12 MB, about 5 s to usable on a slowed phone) before the proof of concept
  goes out; covered by its own task.

Built 2026-10-08:

- Nav wordmark and v2 `<title>` / og:title are "Data Driven Football" (`build_v2_page.TITLE`); the
  classic dashboard keeps its own title. The wordmark links to Trade targets.
- A URL with no known tab (the root, `/v2/`) opens Trade targets; `#player-values` opens Player values.
  The tab order is unchanged.
- At 768 px and up, series read "ESPN · Our value · Week 5" and "FantasyCalc chart · Week 5"; the method
  chips read "Our values" / "Published charts" / "VORP vs waivers"; the legend reads "Solid = our value ·
  Dashed = published chart". Below 768 the short forms stay. Sentences (notes, story, detail) use the
  plain words at every width. The labels re-render when the width crosses 768. Source chips take their
  own row at every width.
- `getHistoryWeeks` lost its reason field: it referred to `HISTORY_UNSUPPORTED`, which the back end
  removed, so the accessor threw and the live week-pair picker showed only the current pair. The
  Risers test caught it.

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

## Compare a trade: named story and league in links (2026-10-08, JEG-454)

Jeremy's answers to the follow-up questions:
- The story card names the sources: "You receive more by A and B. You give more by C. A manager who
  trades off C is the likeliest to accept." (agree: "… by every complete source: A, B and C").
  `TradeValueTrade.tradeStory` returns the series keys per direction.
- A shared trade link carries the sender's scoring, roster and bench share (`&scoring=ppr&roster=QB1.RB2.WR3.TE1.
  FLEX1.SF0.BN6&bench=0.150`), on the assumption that the receiver is in the same league; opening it applies them
  through the engine's setters and says so. The team count is not carried yet.
- `/classic/` is to be retired (back-end ticket JEG-453). v2 signed off (JEG-448).

## Editable position shares (2026-10-08, JEG-452 front end)

- Weights & bench: each position share has a number field (bounds from `getPositionWeightBounds`).
  On Apply, v2 passes only the shares the reader changed to `setPositionWeights`; the engine clamps
  them and splits the rest in proportion, so v2 never rebalances shares itself. Reset defaults calls
  `resetPositionWeights`. A clamped set says so. No copy explains share semantics yet (MR-16).
- Shared trade links carry custom shares (`&shares=QB0.100_RB0.400_WR0.400_TE0.100`) only when they
  differ from the league's defaults, applied after scoring, roster and bench (a league change resets
  shares). A rejected set is ignored.

## Customize, league bar and freshness (2026-10-08, JEG-466 / 462 / 463; spec JEG-474)

Jeremy signed off the source model (JEG-474) on the clickable mock
https://claude.ai/artifact/TYSXr7Wpg4SPiQpu2MTd56.
- The Methods bar is one line: "Showing: 1 projection + 4 adjusted trade charts · Week 5", a legend that
  reads as a legend (symbol + publisher, prior-week badge) and one **Customize** button (`#v2EditSources`).
  Method chips, series chips and the hint line are gone.
- Customize groups series by type with a one-line explanation each, in the JEG-474 vocabulary:
  Projections, Trade charts (adjusted), Trade charts (as published), and Value above waivers folded under
  Advanced. Each group has Select all/none; prior-week series carry a "Wk N" badge and stay selectable;
  unavailable ones are disabled with the reason. A draft until Done; Reset to default restores the
  first-load selection; an empty selection is refused.
- Still to come with the `ddf_value` engine series: section "What goes into DDF Value", DDF Value as the
  default shown series alongside the as-published charts, the shared per-tab picker, and saving choices on
  this device.
- League bar (JEG-462): "Edit league" and "Weights & bench" are equal secondary buttons; no ↗.
- Freshness (JEG-463): one row per root source (publisher) with the week it published and a status of
  Current, Prior week or Not updating. Pipeline steps from `assets/reference-freshness.json`
  (`comparison.source.<src>`, `source_import.<src>`, `source_import.checked_at`, `comparison.built_at`)
  fold into that status: any `freshness_ok: false` shows "Not updating" with "We couldn't refresh <source>
  since <date>". The header chip reads "Week 5 · all sources current", "… N sources on a prior week", or
  "⚠ N sources not updating"; no ↗.

## Back-end requests

**BE-1 · Prior-week values (blocks Risers & fallers, frames 05/06, and every Δ prior week).**
Frame 22: "Δ = current value − prior-week value for that exact pair, recomputed with current league
and weights. No match: 'Δ —' plus a reason, never zero. Never substitute a stale curve or history."
v2 needs, read-only from the engine, something like
`TradeValueCurveControls.getPriorRows()` (or a `prior` map on each `getRows()` row):

- per player_key and per series key, the value the same engine computes from the **prior content
  week's saved inputs** at the **current** league settings and weights (not last week's published
  numbers at last week's settings);
- `null` where that series had no value for the player last week, plus a per-series reason when the
  whole series has no prior week (new source, missing snapshot, paused);
- the prior content week number per series, so the page can label "vs Week N" and refuse a pair
  whose weeks are not exactly one apart.

v2 will compute only `current − prior` per exact pair, as it does for gaps. Until this exists the Δ
toggle stays "Δ —" with the reason, and Risers & fallers stays marked "soon".

Answered 2026-10-08 by the history contract below (branch `feat/week-history`): published charts,
CBS ROS and Razzball get prior weeks, and ESPN, the Adjusted series and the VORP vs waivers series
return "Δ —" with a reason.

**BE-3 · DDF Value for an earlier week pair (Risers & fallers, JEG-465).** `getPriorWeek("ddf_value")`
prices the served pair over the same inputs on both sides. An earlier pair (Week N−1 → N) can only be
built from two `getWeekValues("ddf_value", week)` calls, which may average different inputs, so the Δ
would mix a change of inputs with a change of values. v2 therefore offers only the served pair for DDF
Value. Request: `getWeekPair("ddf_value", week)` (or a `week` argument to `getPriorWeek` that accepts
any saved pair) returning `{values, currentValues, sources, dropped, ...}` over one input set.

**BE-2 · Editable position shares and superflex (frames 11, 12).** Frame 11 lets the reader set QB /
RB / WR / TE shares of total value; frame 12 has a SUPERFLEX slot. The engine exposes
`getPositionWeights()` but no setter, and `setRosterSpot` knows QB, RB, WR, TE, FLEX, BENCH (K and DST
are fixed at 0). v2 needs, in `TradeValueCurveControls`: `setPositionWeights({QB, RB, WR, TE})` with the
feasible bounds per position (like `getBenchBounds`), and a `SUPERFLEX` roster key that the value model
prices. Until then 11 shows the shares read only and 12 says superflex is not supported yet.

Answered 2026-10-08 (JEG-452), position shares, in `TradeValueCurveControls`:

- `setPositionWeights(shares, publish = true)`: `shares` is `{QB, RB, WR, TE}` as fractions of the
  total pie (0.2 = 20%); partial objects are allowed. Named shares are set and the unnamed ones split
  what is left in proportion to their current shares; with all four named they are rescaled to total
  1. Each share is clamped into the bounds and the four always total exactly 1. `null` (or
  `"default"`) resets to the derived defaults. It recomputes and redraws like the other setters and
  fires `trade-value-shared-change` (with `positionWeights`) unless `publish` is false. Returns
  `{ok: true, weights, requested, clamped, isDefault}`; invalid input (unknown key, non-number, empty,
  not an object, engine not loaded) returns `{ok: false, error}` and changes nothing.
- `resetPositionWeights(publish = true)`: same as `setPositionWeights(null)`.
- `getPositionWeightBounds()`: `{QB: [0.01, 0.97], RB: ..., WR: ..., TE: ...}`, or `null` before the
  engine has loaded.
- `getDefaultPositionWeights()`: the derived defaults (from the calibration pies) for the active
  scoring and teams; `getPositionWeights()` is the active shares.
- A scoring or teams change resets the shares to that league's defaults. How far an edit reaches
  (today: the live calibration, the ESPN anchor and the `*_adjusted` series) is open as
  `docs/math-review-agenda.md` MR-16.

**BE-4 · Per-value missing reasons (2026-10-08).** Confirmed by the back end: `row.missingReasons[seriesKey]`
(string) for every null value (adjusted fallbacks such as "Not enough players to fit an adjustment" or "Adjustment fit
refused (order would invert)", shallow charts, held or not-yet-published sources, `ddf_value`). v2 reads it through
`missingReason()`; until it ships, v2 shows its generic reason.

## Back-end contract: native rank (JEG-482, 2026-10-08)

A published chart's Indexed ("as published") values are its native values times one factor, so the
chart's own order is kept at every league setting (methodology, The Three Views). The front end can
now say where the publisher itself ranks a player, read-only, in `TradeValueCurveControls`:

- `getNativeRank(playerKey, source)`: the player's rank on that publisher's own list at the active
  scoring (its superflex list when the roster has a superflex slot and the publisher publishes one),
  1 = highest native value; ties share the better rank. `null` when the chart does not price him or
  `source` is not a published chart (`fantasycalc`, `usatoday`, `fantasypros`, `cbs`). Use it for
  "#3 on FantasyCalc" next to the Indexed value in the player drawer and the table tooltip.
- `getNativeRanks(source)`: every rank as `{playerKey: rank}` (one call per chart for a table),
  or `null` for a source that is not a published chart.

Ranks are over the charted players (canonical QB/RB/WR/TE), so a publisher list that includes
K/DST or unmatched names can show a slightly different number on its own site. The rank
guard (`dist/modules/rank-guard.json`, schema `rank-guard-v1`) and
`TradeValueCurveDiagnostics.indexedOrder` report whether the Indexed order matches it.

## Back-end contract: history

Built 2026-10-08 (branch `feat/week-history`) for Risers & fallers (frames 05/06) and the Δ
prior-week filter. It applies frame 22 as written: Δ = current value − prior-week value for that
exact pair, recomputed with the current league and weights. If there is no match, show "Δ —" plus a
reason, never zero, and never substitute a stale curve or history.

### What is served

`assets/history/index.json` and `assets/history/week-<N>.json`. `make sync` copies them from the
committed store `data/history/`. Each file is versioned by `schema` (`week-history/1`,
`week-history-index/1`).

- `week-<N>.json` = `{schema, season, week, frozen, sources: {<source>: entry}}`. An entry has:
  - common fields: `source`, `week`, `kind`, `week_evidence`, `origin`, `fingerprint`, `complete`
    and `captured_at`;
  - published charts (`kind: "published_chart"`: usatoday, fantasycalc, fantasypros, cbs):
    `natives: {standard|half_ppr|ppr: {player_key: native}}`. These are the chart's own
    as-published values for the saved 12-team, 1-QB setup. They are the same cells the engine
    derives the chart from, taken from Supabase `public.source_trade_values` /
    `public.cbs_trade_values` (every saved bake is a version; the week's snapshot is chosen by the
    rule below);
  - projection sources (`kind: "projection"`: espn, cbsros, razzball): `field` (`espn_ppg`,
    `cbsros_ppg`, `rz_ppg`), `snapshot_date` and `ppg: {player_key: [standard, half_ppr, ppr]}`.
    These are per-game projections rounded to `PPG_DECIMALS`, as `bake_players.py` rounds them, taken from
    the served players.json or the Supabase projection tables.
- `index.json` = `{schema, season, content_week, fixture_built_at, weeks: {"N": {file, frozen,
  sources: {s: {origin, complete, fingerprint, content_date?, pulled_at?}}}}, served: {s: {week,
  label_week, fingerprint, version?, label_mismatch? | reason?}}}`. `served[s].week` is the saved
  week whose inputs equal what the page serves now; `version` is `"snapshot"` (the week's
  snapshot) or `"superseded"` (another kept version of that week, e.g. an older revision still
  served, or a FantasyCalc pull newer than the Tuesday cut). Then `entry_fingerprint` names it,
  `make sync` serves it in `assets/history/served.json` (`{schema, season, sources: {s: entry}}`),
  and `getWeekValues(s, served week)` prices that version, so "this week" is exactly the chart. It is matched by content fingerprint, not by the
  section's label. `label_mismatch` says when the two disagree.

### How weeks are coded (docs/week-coding-rules.md)

The week comes from the content. Projections and USA Today / FantasyPros use the content date on
the Tuesday-flip calendar (`pipelines/nfl_week.py`). CBS uses the article's week column, and the
pull cannot predate that week. FantasyCalc is a live value, so it uses the week column, and the
pull must have been made in that week. `build_week_history.validate_week_doc` refuses any entry
whose evidence gives a different week than its file, so a Week 4 file cannot carry Week 3
content. `make sync` validates every file and stops on a bad one.

### Which snapshot is a source's week (week-over-week rule, 2026-10-08)

Sources save many versions: article revisions, daily projection snapshots, repeated FantasyCalc
pulls (and, with the refresh-cadence lane, hourly ones). For each source and content week N
exactly one saved version is **the week-N snapshot**; Δ and Risers & fallers compare against it.
`pipelines/build_week_history.py` (`select_week_snapshot`) implements this; the content
calendar is `pipelines/nfl_week.py` (Tuesday flip).

| Source | Week N is | Week-N snapshot (one of many) |
| --- | --- | --- |
| USA Today, FantasyPros, CBS (articles) | the article for Week N (content date, or CBS's article week) | the **latest revision** of that article saved before week N freezes (the first capture after the Tuesday turnover to N+1) |
| FantasyCalc (continuous crowd value) | pulls made during content week N | the **first pull at or after Tuesday 12:00 UTC** of week N (the cut: after Monday-night reaction, when the Week-N articles are out). No pull after the cut in week N: the week's latest pull, flagged `cut: "missed"` |
| ESPN, CBS ROS, Razzball (projections) | snapshots dated in week N | the **newest snapshot dated in week N**, i.e. the last one before the Tuesday turnover |

- While week N is open, its snapshot is provisional and follows the rule as new versions arrive
  (articles and projections: newest; FantasyCalc: the cut pull once one exists, then fixed).
- Once week N freezes, its snapshot never changes. A revision of the Week-N article saved later
  is kept as a late version, never swapped in, so a published Δ cannot change after the fact.
- Every other saved version of the week is kept in `data/history/superseded/week-<N>.json`
  (not served; not read by the engine). A mid-week replacement therefore keeps both.
- "This week" in Δ is what the page serves now (matched by content fingerprint to a saved
  version of week N, selected or superseded); "last week" is week N−1's snapshot.
- Review drift (`review_comparison_candidate.native_drift`) compares a candidate with what is
  served, not with this rule: it guards the promotion, not the week-over-week reading.

### Append-only

A week freezes once the calendar has moved past it. A frozen entry is never replaced by different content: a different
candidate is reported and dropped. The only replacement allowed is the same content (same
snapshot or pull, same players, every saved value a rounding of the new one) at finer precision,
for example when bake_players changed per-game rates to 6 dp. A source missing from a frozen week can still be added when
its genuine content for that week turns up. The open week keeps the newest content seen. The
rebuild chain (`rebuild-chain.yml`, step "Capture week history") runs
`pipelines/build_week_history.py --supabase` before the chain and commits `data/history/` with
the fixture. `make sync` also saves the served players.json projections (`--served-only`).

### Engine accessors (read-only, both return Promises)

- `TradeValueCurveControls.getPriorWeek(source[, week])` resolves to `{source, week, available,
  reason?, values, setting, origin, fingerprint, method, currentWeek, priorWeek, labelMismatch?}`.
  - `priorWeek = served[source].week − 1`. Passing a `week` that is not exactly that returns
    `available: false`.
  - `values` is `{player_key: value}`. A player the saved week does not price is absent, not 0.
  - `setting` is the scoring, teams, roster, bench share, view and weights it was priced at.
- `TradeValueCurveControls.getWeekValues(source, week)` returns the same object for any saved
  week.

It recomputes with the engine's own functions at the reader's current league, roster, bench
share and weights, and against the current common scale. Only the source's own inputs come from
the saved week. The common scale is the positional maxes from our ESPN projections, the ESPN
anchor, and the other charts served now as waiver-line peers. So a chart's Δ is that chart's
movement, not a move in our projections.

- Published charts: `ValueModel.derivePublishedSetup` on the saved natives. This is the function
  that prices the chart off the saved setup, and it reproduces the saved values on it.
  - VORP vs waivers / Adjusted values tabs (JEG-479, 2026-10-09): `ValueModel.derivePublishedViews`,
    the current week's batch, on every chart's saved natives for that week (own natives and player
    set, peers, the Adjusted 0-70 batch) with the current league, roster and anchor group totals.
    Equal natives keep the served list's order (the saved files store natives by player id). A
    chart with nothing saved for the week is out of that week's batch. Every setting derives the
    tabs live since VA-3 (Jeremy, 2026-10-09: "Compute live everywhere."), Full PPR / 12 / standard roster
    included. Proof: the served week fed back reproduces each chart's tab values exactly.
- CBS ROS and Razzball: `ddfTwoTierValuesForSource` on the saved projections, then
  `normalizedAdjustedMapFor`, with the same below-the-leg 0 rule as the table.
- ESPN (2026-10-08, HISTORY-ESPN-PRIOR): that week's two-tier leg, built by the pipeline's own
  leg code (`build_week_history.espn_legs_for_week`: `build_ddf_two_tier_leg` tiers and
  `calibrate_tiers` at 12 teams and the 0.15 reference share, one 70/max scale, 1 dp as the
  fixture) from the saved `espn_ppg`, served as `assets/history/espn-legs.json` (rebuilt by
  `make sync`, not stored). It then takes the anchor's own path: the live cells at the active
  bench share, the roster shape, and the table's display rules (ESPN lists the player at 0 → 0.0;
  at or below the leg's lowest priced projection → 0.0). The served week's rebuild equals the
  fixture's ESPN leg on every priced player. ESPN weeks saved before 2026-10-08 do not carry
  ESPN's "projects 0" players, so in those weeks such a player is absent ("Δ —"), not 0.
- VORP vs waivers (`espn_vorp`, `cbsros_vorp`, `razzball_vorp`): `buildVorpRows` on the saved
  projections of the base source, level-matched to the current anchor (`scaleToSharedTotal`)
  like the served series.
- Adjusted (`*_adjusted`): the saved chart priced as above, then the CURRENT fit's cells
  (`buildLiveAdjustedMap`) and `normalizedAdjustedMapFor`. Δ is the chart's movement through one
  fit; a refit between weeks does not show up as movement. Indexed view only, and unavailable
  while the Adjusted series is paused.
- `getPriorWeek(series)` for a VORP or Adjusted series uses the served week of its base source
  (`espn_vorp` → `espn`, `cbs_adjusted` → `cbs`).

Proof that this is the engine's math: `getWeekValues(source, served week)` equals the chart's
current values for every player in every one of the 12 scoring × team combos, and on a custom
roster (`tests/test_week_history.py`), for all 14 series. ESPN allows only players priced 0.0 on
one side and absent on the other (two players whose players.json ESPN status and the leg
disagree; GAP-ESPN-LEG-STATUS-EDGE).

### How the front end computes Δ

For each exact pair (player, series), call `getPriorWeek(series)` after every
`trade-value-rows-change`, because the values depend on the setting.

- If `available` is false, show "Δ —" plus `reason`.
- If the player has no prior value, show "Δ —" with "not on <source>'s Week N chart".
- Otherwise Δ = `row.values[series] − values[player_key]`, labelled "vs Week `priorWeek`".

Never compute Δ across two series, and never fill a missing prior value with 0 or with the current
value.

### What is saved (2026-10-08)

| Source | W2 | W3 | W4 | W5 (open) | Served now |
| --- | --- | --- | --- | --- | --- |
| USA Today | 09-15 | 09-23 | 09-29 | 10-06 | W5 → prior W4 |
| FantasyCalc | pull 09-16 | pull 09-23 | pull 10-05 | pull 10-06 | W5 → prior W4 |
| FantasyPros | 09-15 | 09-22 | 09-29 | 10-06 | W5 → prior W4 |
| CBS | article W2 | article W3 | article W4 | — | W4 → prior W3 |
| ESPN | 09-17 | 09-22 | 10-03 | 10-07 | W5 (prior not recomputed) |
| CBS ROS | — | — | 10-02 | — | W4 → no W3 saved |
| Razzball | — | 09-22 | 10-01 | 10-06 | W3 (labelled W4) → no W2 saved |

### Capture cadence (refresh-cadence lane, 2026-10-08)

How the versions the week-N snapshot rule chooses from get saved (docs/methodology.md "Refresh
Cadence"):

- FantasyCalc: probed hourly; a changed list is saved at most every 6 h, plus the fixed Tuesday and
  Friday 13:07 UTC saves. Every save is its own bake, `fcwk<N>_<YYYY-MM-DD>t<HHMM>_v1` (it was one
  bake per UTC day, so a later same-day save overwrote the earlier one). The Tuesday 13:07 save
  guarantees a pull at or after the 12:00 UTC cut; a probe-driven save between 12:00 and 13:07
  can be the cut instead. `pulled_at` is set on every row.
- Articles (USA Today, FantasyPros, CBS): probed every 3 h Monday to Thursday and every 12 h Friday
  to Sunday, so a revision is saved within 3 h midweek. CBS is read from www.cbssports.com: the
  sportsfly.cbsistatic.com mirror served a day-old revision on 2026-10-08.
- Projections (ESPN, CBS ROS, Razzball): probed every 4 h with the last slot at 23:25 UTC, so a
  Monday change is saved inside week N, and re-scraped at least every 20 h even when unchanged.

## Back-end contract: DDF Value (JEG-471 / JEG-479 / JEG-497, 2026-10-08/09)

> **Superseded (JEG-508)** once the Value Pipeline implementation merges. The
> target contract is `docs/methodology.md` VP-11:
> - The inputs are the source keys and their Adjusted values. The
>   `*_adjusted` keys are retired.
> - There are three versions, `ddf_value`, `ddf_value_charts` and
>   `ddf_value_projections`, each one number in every tab (shipped with JEG-497, #465).
> - `ddfByVersion` replaces `ddfByView` (shipped with JEG-497, #465).
> - The composite calls take a `version` instead of a `view`.
> - There is a new `TradeValueCurveDiagnostics.valuePipeline`.
>
> Every other field name below keeps its meaning. Until then, this section
> describes the engine.

The DDF Composite Value (rule: `docs/methodology.md` "DDF Composite Value") is an engine series in
three versions: `ddf_value` (all seven inputs), `ddf_value_charts` (the four published charts) and
`ddf_value_projections` (ESPN, CBS rest of season, Razzball). v2 reads them; it does no blend math.
Each is the equal-weight mean of its inputs' **Adjusted values** only, ONE number per player, the
same in every view and tab, for the current and the prior week over the same inputs. One input
pricing a player gives that value, flagged low confidence; none gives no value (Jeremy 2026-10-09).
Input keys: `espn, cbsros, razzball, fantasycalc_adjusted, usatoday_adjusted, fantasypros_adjusted,
cbs_adjusted` (a chart input is the chart's Adjusted values, series `<chart>_adj_values`).

**Stable for v2 (lead, 2026-10-08/09).**
1. `values.ddf_value` is the blended DDF Value and does not change with the view tab. v2 reads that
   key; `values.ddf_value_charts` and `values.ddf_value_projections` are the other two versions.
2. When a version is null, `row.missingReasons[version]` is a string (today always "No source
   prices this player"); for the blend also `row.ddfReason`.
3. In `getCompositeInputs().excluded`, an input the reader deselected has the exact reason
   `"not selected"`; v2 lets readers re-tick only those. Every other reason is a different,
   human-readable string shown disabled: `held: <reason>`, `not yet published for week N`,
   `no prior week: <why>`, `missing from this build`, `not available for <scoring> / <teams>
   teams`. A held or unpublished input reads as such even when it is also deselected.
4. `getPriorWeek(version)`: **Δ = `currentValues[pk]` − `values[pk]`**.
5. `setCompositeInputs(list)` silently drops held and not-yet-published keys and succeeds, so a stale
   saved list still works; v2 re-reads `getCompositeInputs()` afterwards.

- **Rows.** Every `getRows()` / `getAllRows()` row has:
  - `values.ddf_value`, `values.ddf_value_charts`, `values.ddf_value_projections` (number or `null`).
  - `ddfCount`, `ddfChartsCount`, `ddfProjectionsCount`: inputs pricing him in each version.
  - `ddfLowConfidence` + `ddfConfidenceNote` (blend), `ddfChartsLowConfidence`,
    `ddfProjectionsLowConfidence`: `true` when exactly one input prices him (the value is that
    input's); the note is "Only one source prices this player", else `null`.
  - `ddfSources` (blend: the series averaged for him), `ddfReason` (blend, `null` with a value).
  - `ddfPrior`, `ddfPriorCount`, `ddfPriorLowConfidence` (blend, prior week, same inputs).
  - `ddfTier` (`"starter" | "bench" | "waiver"` by the blend; `null` without one; a one-source
    value counts).
  - `ddfByVersion: {blended, charts, projections}`, each `{value, count, sources, reason,
    lowConfidence, confidenceNote, prior, priorCount, priorLowConfidence}`.
  - `getPlayerValues()` also carries the three version keys.
- **Missing values (JEG-479, 2026-10-09).** Every row has `missingReasons: {[seriesKey]: string}`
  with an entry for each `null` in `row.values` (and none for a number). Texts: `Chart doesn't list
  players this deep at <pos>` (a published chart too shallow there; a fully loaded chart gives 0
  instead, `docs/methodology.md` "Published Charts On The Rows"), `Not enough players to fit an
  adjustment` / `Adjustment fit refused (order would invert)` (a `*_adjusted` identity-fallback
  cell), `Adjustment data failed to load` (every `*_adjusted` null when `getLoadStatus()` reports the
  adjustment inputs failed), `<ESPN | CBS rest of season | Razzball> doesn't project this player`,
  `No adjustment for this player's group`, `Missing from this build`, `Paused while it waits on
  fresh adjustment inputs`, `Not available for <scoring> / <teams> teams`, and for the three DDF
  keys "No source prices this player". A held or not-yet-published series keeps its kept section's
  values, so it is not null for that reason; its DDF exclusion is in `getCompositeInputs().excluded`.
- **Rank and zones.** `setLockOrder("ddf_value")` ranks by the blend and `getRankSource()` returns
  `"ddf_value"`; the lock survives scoring, team and view changes. `getZones()` then sits at the DDF
  tier counts in a position view (All: teams × slots, as for every series).
- **Source info.** `getSourceInfo()` is unchanged (plotted series only).
  `getSourceInfo({includeComposite: true})` appends one entry per version: `{key, label ("DDF
  Value", "DDF Value (charts)", "DDF Value (projections)"), longLabel, composite: true, inputs,
  series, isDefault, week, priorWeek, stale: false, available, active: false, ...}`. None is in
  `getActiveSources()` or drawn.
- **Inputs.** `getCompositeInputs([version])` (`version` is `"blended"` (default), `"charts"`,
  `"projections"` or the matching `ddf_value*` key; anything else reads the blend) → `{version, inputs, series,
  requested, isDefault, defaults, allowed, excluded: [{key, series, reason, ...}], held,
  notPublished, currentWeek, priorWeek, priorAvailable, priorReason, minSources: 1}`. `inputs` are
  the input keys averaged in that version and `series` the series they contribute. A held entry
  also has `heldBy` (the section carrying the hold), `holdField` (`validationHold` |
  `promotionHold`), `holdWeek`, `holdRoot` (the source whose disagreement caused it) and
  `holdKeptWeek`; an unpublished one has `notPublished: true`. `defaults` are the inputs a reader
  can choose this week. `setCompositeInputs(keys, publish = true)`: `keys` is an array of the seven
  keys (order and duplicates ignored), `null` or `"default"` restores the defaults (choosing exactly
  the defaults is the default); every version uses its share of the choice. Held / unpublished keys
  are dropped and listed in `dropped`; if that leaves no usable input the defaults apply
  (`fellBackToDefaults: true`). Returns `{ok: true, ...getCompositeInputs()}`; an empty array, an
  unknown key, a non-array, or a list with no usable input and nothing dropped returns `{ok: false,
  error}` and changes nothing. It recomputes only the DDF fields, redraws, fires
  `trade-value-rows-change`, and (unless `publish` is false) `trade-value-shared-change` whose
  detail carries `compositeInputs` (`null` = defaults). `resetCompositeInputs(publish = true)` =
  `setCompositeInputs(null)`. Chosen inputs persist across league changes; one unavailable at a
  setting is skipped there.
- **Values.** `getCompositeValues([version])` → `{version, inputs, series, currentWeek, priorWeek,
  priorAvailable, priorReason, current, currentCounts, prior, priorCounts, minSources}` (objects
  keyed by `player_key`; players without a value are absent; `prior` is `null` without a prior
  week).
- **Recompute.** Every rebuild (scoring, teams, roster, bench share, position shares) recomputes the
  three versions. A view switch leaves them unchanged.
- **History.** `getPriorWeek(version[, week])` resolves to `{source, week, available, reason?,
  values, counts, currentValues, currentCounts, sources, seriesValues, dropped: [], inputs, series,
  excluded, currentWeek, priorWeek, version, minSources, setting, method}`. `sources` are the series
  averaged in both weeks; `currentValues` equal the rows' `values[version]` and `values` its prior;
  `seriesValues` is each input's prior week as averaged (a chart's with the rows' chart rules). An
  input without the prior week is not in either week (it is in `excluded` with `no prior week:
  ...`). Label it e.g. "DDF Value · 3 of 7 sources" from `inputs.length`. `getWeekValues(version,
  week)` gives `{values, counts, sources, dropped, ...}` for any saved week over the same inputs;
  `getHistoryWeeks(version)` the saved weeks any input has. The per-series `getWeekValues` /
  `getPriorWeek` return a saved week as priced (no row rules).
- **Today's data.** Since JEG-479 "Build prior week" and VA-3 (Jeremy, 2026-10-09: "Compute live everywhere.",
  the saved `vorp_views` retired) every chart has earlier Adjusted values at every setting, so all
  seven inputs count in both weeks.

## Multi-device pass (2026-10-08)

Swept every tab at 390, 768, 820, 1024 and 1440 in light and dark (`tests/test_v2_ux_render.py`).

- Tablet (768–1023): the tabs were off screen past "Trade targets"; they now sit on their own row.
  The Methods row's source chips were squeezed into a one-chip column; they now take a full row.
- 44 × 44 hit areas (frame 17): tabs, zoom −/+, rank-window buttons and the brand link were 32–40 px.
  Chips and sort headers keep their compact look with an invisible 44 px hit box; chip rows have
  12 px between rows so neighbouring hit boxes do not overlap.
- Dark mode: hovered table rows, the status toast and the "Indexed" chip used light-only colours (a
  hovered row went near-white under light text). They now use tokens with dark values.

## Risers & fallers tab and Δ prior week (frames 05 / 06, built 2026-10-08)

Built on the back-end history contract above (`getPriorWeek`), which answers BE-1, then brought in line
with frames 05/06 (see "Aligned with the frames" below; the table became two cards).

- `v2/#risers-fallers`. One exact series at a time, picked under "Source:"; a series the engine has no
  prior week for is listed disabled and named in the note with the engine's reason (today ESPN, the
  Adjusted series, VORP vs waivers and CBS rest-of-season). Default: the first series with a prior week
  (FantasyCalc · Index).
- Δ = this week − the engine's recompute of last week, at the reader's league (`app/v2/movers.js`, the
  tab's only arithmetic). Risers: Δ > 0, largest first; Fallers: Δ < 0, most negative first; a Δ that
  shows as 0.0 is neither and is counted. A player without a prior value is left out and counted, never 0.
- Columns: Player, Pos, Team, Week N (tinted), Week N−1, Δ (▲ / ▼ + signed number). Cards below 768 px.
  Position is the shared engine setting.
- Prior-week results are cached per series and dropped on every `trade-value-rows-change`.
- Player values, Δ prior week on: every series cell shows `Δ ±x.x` (hover: "vs Week N: value") or
  `Δ —` with the engine's reason; the note under the filters lists each plotted series' prior week or
  reason. With the first-use DDA selection every Δ is "Δ —" (ESPN and Adjusted have no prior week);
  adding an Indexed chart shows real Δ.

## Shareable trades and page metadata (2026-10-08)

- Compare a trade keeps its sides in the address: `v2/#compare-trade?give=<player_key,…>&get=<…>`.
  "Copy link to this trade" copies it (falls back to showing the link if the clipboard is blocked).
  Whoever opens it sees the same players, priced for their own league settings; an unknown key is
  listed and turns every row it touches into —; a repeated key is read once.
- `build_v2_page.py` sets `color-scheme: light dark` (v1's `light` kept selects light inside v2's dark
  theme) and the v2 nav colour as `theme-color`.

## Compare a trade: waterfall and verdict (JEG-468/469)

Built 2026-10-08. Supersedes the "no overall verdict" line of the frame 07/08 section: there is still
no blended score, but one series now gives a verdict.

- **Verdict (Jeremy, 2026-10-08).** "Primary thing that matters is that DDF thinks you win, and it can
  be better if the other sources DON'T agree." The card reads ONE series, `verdictKey()` in v2.js,
  which is "Player values shown" (`TR.shown`) until the engine exposes DDF Value; swapping that one
  line is the whole change. Headline: "<series>: you win by +6.2" / "you lose by −3.1" / "an even
  trade, 0.0", with ▲ / ▼ / = and the card edge colour. Text: on a win, the complete series that call
  it a loss, as the selling point ("A and B think you lose this trade. A manager who trades off A or B
  is the likeliest to accept."); every source agreeing is said as harder to get accepted; on a loss,
  the sources that think you win are named and the reader is told to rework the offer. Incomplete
  rows never count and are listed as not counted. Logic: `TradeValueTrade.tradeVerdict` (pure, in
  trade.js, `tests/test_v2_waterfall.py`).
- **Story card** (`tradeStory`) is folded into the verdict card as a disclosure, open by default only
  for the same-publisher contrast (the one thing the verdict does not say). Same ids and logic.
- **Waterfall (JEG-468).** Each row of "Difference by source & method" replaces the diverging net bar
  with three lanes on one shared scale: give steps (largest first, "Henry −47.5", give colour) down
  from 0; receive steps (largest first, "+55.1", receive colour) up from where the give steps ended
  (a dashed link marks the turn); a landing bar from 0 to the net, coloured by sign with ▲ / ▼ and
  the signed net. A 2px tick marks 0. The scale is the largest cumulative extent across rows (0
  included), so a big 2-for-2 with a small net reads as a small net. A player without a value is a
  hatched "— Name" step that moves nothing, later steps are partial, and the row has no landing
  ("No result: a value is missing"). Every step is focusable (`role="img"`, aria-label "Give Henry
  −47.5, running −47.5") and shows the shared tooltip on hover or focus (player, series, value,
  running total). Labels shorten to the value, then to nothing, on narrow steps; the tooltip and
  text alternative always carry everything. Steps come from `TradeValueTrade.waterfall` /
  `waterfallScale` (pure). VORP vs waivers rows get the same waterfall, each on its own scale (those
  scales are not comparable). "Show players ▾" is kept as the table fallback.
- **Verdict waterfall.** The verdict card repeats the verdict series' waterfall on the table's scale,
  so the deciding series' steps are above the fold at 1366×768 even though the table starts below.
- **Layout (JEG-469).** ≥1280: You give | You receive | Verdict. 768–1279: two input columns, verdict
  as a full-width strip under them. <768: stacked; once both sides have a player, a fixed bar at the
  bottom carries the verdict headline (hidden while the verdict card itself is on screen; tapping it
  scrolls to the card). Header: H1 27px, subtitle one line and dropped once a player is added; picker
  and Swap / Clear inline in the header row; `#v2Compare` padding-top 16px (scoped, other tabs keep
  28px). Cards: padding clamp(14–16px), h2 16px, title and search on one row from 1024, 36px inputs
  (44px hit area through the label), side total pinned to the card foot. Spacing uses
  clamp(10px, 1.1vw, 16px).
- **Deviation:** player rows are 44px, not ~36px: the 44 px target rule wins over the ticket's ~36.
- **Example empty state.** With no player added, `TradeValueTrade.pickExample` picks a 2-for-2 from
  the top 12 players by the verdict series that every selected series prices, preferring one the
  verdict series calls a win and the most other series call a loss (then the smallest such win).
  Marked "Example" in a banner, the verdict eyebrow and the table meta; side cards dashed; no remove
  buttons, no share link, nothing in the address. "Use this example" copies it onto the sides.
- **Not done:** switching the verdict to DDF Value (waits for the engine series).

## Trade targets: review fixes (JEG-456/458/459/461/464, 2026-10-08)

- Copy (JEG-464): H1 "Where the trade market is wrong this week"; subtitle "We check four published
  trade charts against our projection-based values for your league. Sell the players they overpay
  for; buy the ones they undervalue." Nav label unchanged ("Trade targets", "Targets" on phones).
- Both lists at once (JEG-461): the Sell/Buy toggle is gone. Sell and Buy are two cards
  (`#v2TSell` / `#v2TBuy`), side by side from 1280 px, stacked (Sell, then Buy) below; phone cards
  stack the same way. Each list opens on its top 5 by largest gap with a full-width
  "Show all N sell targets ▾"; that shows 25, then "Show more (25 of N)" adds 25 at a time, and
  "Show top 5" collapses. State is per list (`T.shown.sell` / `T.shown.buy`) and resets when a filter
  changes. Filters are one row (search, position, our value, compare against + caption + ⓘ); the
  "players left out" note moved below the lists. At 1440 × 900 and 1366 × 768 the H1, subtitle and
  the top 5 of both lists are above the fold.
- Two-column rows are compact: Player (with Pos · Team · Tier), Our value, Largest gap with the chart
  it came from, and a 44 px ▾ that opens the row's per-chart values (value, gap, badge) underneath.
  The per-chart cells stay in the DOM but are hidden at ≥1280 px. The player drawer is unchanged.
- Fits the window (JEG-456 part 1): the Pos / Team / Tier columns are gone at every width (they were
  already in the player sub-line, which now always shows); headers wrap to two lines; cell padding
  and number size use clamp(). No sideways scroll from 1024 px (checked at 1024, 1100, 1279).
  Part 2 (tier from the composite) waits on an engine series.
- Indexed label (JEG-458): chart headers read "Wk 5 · indexed"; "Compare against" has the caption
  "Indexed to our scale". An ⓘ (`indexedInfoButton()`, 44 px, `aria-expanded`, Enter opens, Esc or a
  click outside closes and returns focus) sits beside "Compare against", in each chart column header
  and in the Largest gap header; it opens the explanation with a link to How values work. It stops
  propagation, so it never opens a player. The per-value hover math is JEG-457 (not built).
  `closePopover()` now resets `aria-expanded` on any anchor that set it to true.
- Prior-week badge (JEG-459): `priorWeekInfo(key, item, refWeek)` / `priorWeekBadge(...)` in v2.js
  are shared helpers for any tab. Badge text "Wk 4" in the older-week colour, tooltip and accessible
  name "FantasyPros has not published Week 5 yet; showing Week 4." (refWeek = freshness
  `current_content_week`, else the engine reference week). Current-week sources get none. On this
  tab it appears in the #v2TChart option text (and beside the caption when that chart is picked),
  column headers, Largest gap attribution, opened rows, phone cards and the footnote.
  `chartsToCompare()` in targets.js now returns `{used, skipped, prior}`.
- Compatibility hook: the two list headings carry `data-side="sell"` / `data-side="buy"`, and the sell
  list keeps the ids `#v2TTable` / `#v2TCards`; the ESPN-0 and below-waiver-line render suites click
  `#v2Targets [data-side=sell]` and read `#v2TTable`.
- Tests: tests/test_v2_targets_render.py (numbers for both lists, opened rows and cards; layout,
  fold, paging, popover, simulated prior week; 12 broken-build mutations) and tests/test_v2_targets.py
  (prior-week charts compared and flagged).

## Player values: toolbar, brushes, table fit (JEG-470/472/473/475)

Supersedes the Player values parts of "Chart options (21)" and "Navigator and value range (24)" above.

- **One toolbar (JEG-475).** Search · Position · Show · Rank by · Δ Prior week · More · Reset, in that order,
  sticky at 768 px and up. "Show" is one range control (All / Top 25 / 50 / 100 / Starters / Bench / Waiver;
  the last three are the engine's `getZones()` boundaries as before). A brush drag, zoom or exact ranks turn it
  into "Custom lo–hi" (the ranks actually shown). More holds only exact From / To ranks. Reset clears search,
  position, Show (back to Top 100), value range, sort and Δ; rank by, sources, columns and league stay (they are
  selections, not filters). Removed: the chart-card rank-window buttons, the Chart options button and panel,
  Reset to all, Reset zoom, Clear filters and the Value range button. Y-axis custom bounds and Hide zero-value
  tail were dropped (the Y brush covers the first; nothing used the second). The empty state keeps its per-filter
  buttons; "Clear all filters" there runs Reset.
- **Show drives the chart and the table.** Shown players = rank window ∩ value range. Before, the window was
  chart-only and the table listed everyone; the table now lists the shown players (Show more pages by 50).
- **Y value brush (JEG-472).** A vertical brush beside the plot, styled like the X brush, over the ranking
  series' full spread for the listed players, with a value histogram (square-root scaled) as its overview and
  labels at the thumbs. Two `input[type=range]` with `aria-orientation="vertical"` and `aria-valuetext`
  "Value 12.5"; arrows step 0.5, PageUp / PageDown jump a tenth of the scale; the track ends mean open ended.
  It writes the same `state.range` as "Set exact values" (the frame 24 popover, now a small link in the plot's
  corner under the brush). Below 768 px the brush is hidden and the link is the control. The "N players
  omitted: no … value" count still shows.
- **Inside the chart** only direct manipulation: Y brush, X brush (labels at its thumbs) and zoom − / + as 44 px
  overlay buttons in the plot corner. The legend sits inline after the chart title; it names publishers (the line
  style carries the method) and ends with the line-style key for the styles drawn ("Solid = our value · Dashed =
  published chart"; short forms below 768).
- **Table (JEG-473).** A grouped top row by each series' existing method (Projections = DDA of a projection
  publisher in `KIND`; Trade charts adjusted = other DDA; Trade charts as published = Indexed; VORP vs waivers;
  Spread) plus "Ranking" over the ranking column. Headers: publisher on line 1, method in small caps on line 2
  (week only for an older series); sort arrows show on the sorted column and on hover. Pos / Team / Tier fold into
  the player sub-line below 1600 px; at 1600 px and up they get columns only while the table still fits (otherwise
  they stay folded, so the table never scrolls sideways). Numbers 13 px tabular, right, one decimal, 6–8 px padding;
  rows about 34 px. Sticky header rows and sticky # / Player columns inside the table's own scroll box. Heat tint:
  three pale steps above (green) or below (red) the same row's ranking value (5 / 15 / 30 % apart), DDA and Indexed
  only, never against VORP; colour only, and every cell's title and screen-reader text says above / below /
  about level. Missing = "—" with the reason in its title. Columns menu: hide value groups (never the ranking
  series) and Position / Team / Tier.
- **Above the fold (JEG-470).** From 1280 px the chart card and the table card sit side by side
  (`minmax(420px, 1fr) fit-content(64%)`); the table card takes the chart card's height and scrolls inside. Below
  1280 they stack and the table box is capped at the viewport. Measured (default selection): 1440 × 900 chart card
  ends at 817 px with 9 rows visible; 1366 × 768 ends at 761 px with 6 rows; 1280 × 800 no sideways scroll.
  H1 26–28 px; the slogan is "Trade values for every player, tuned to your league · Week N" (week from the
  freshness data, else `getReferenceWeek()`).
- **Density tokens** in `:root` for every tab: `--v2-pad-card`, `--v2-pad-card-x`, `--v2-pad-section`, `--v2-gap`,
  `--v2-title-1`, `--v2-title-2`, `--v2-row-h`, `--v2-cell-pad-x`, `--v2-group-h`, `--v2-chart-h`, plus
  `--v2-heat-*` (light and dark). `--v2-chart-h` = `clamp(280px, calc(100vh - 490px), 42vh)`: the 490 px is the
  shared header plus the toolbar at 1366 × 768; if the Methods bar merge makes the header shorter, the chart
  simply grows. Stacked layouts (768–1279) use `clamp(280px, 36vh, 400px)`.

## Data fidelity: freshness fails closed, bench share shown as used (2026-10-08, fe-fidelity)

- **Source freshness fails closed.** A source shows "✓ Current" only when its own rows in
  `assets/reference-freshness.json` (`comparison.source.<pub>` and `source_import.<pub>`) both report
  `freshness_ok === true`. A missing or unreadable file, or a missing row, shows "? Freshness unknown" (amber,
  "We couldn't confirm when X last updated."), never a tick. "Not updating" and "Prior week" are unchanged and
  take precedence. The header chip says "all sources current" only when every root source is confirmed; otherwise
  e.g. "Week 5 · ⚠ 2 sources unconfirmed" (and "checking sources…" until the file has loaded).
- **Bench share shown is the share used.** Below a position's feasible window the engine prices at a higher share
  (`bench_share_used`; PPR 12 teams at 2%: QB 7.5%, RB/WR/TE 4.4–4.7%). v2 reads it from the new read-only
  `TradeValueCurveControls.getBenchShareUsed(share?)` (per position, null when withheld) and shows the lowest–highest
  used share in the Weights & bench readout and Starters / Bench split, on How values work, and in the shared-link
  notice. When it differs from the request one note says so: "Bench 2.0% requested · priced at 4.4–7.5% (lowest
  the league supports)". The slider position and the share link (`bench=`) still carry the request. The
  "Bench share moved from … to …" league notice is about the setting and is unchanged.

## DDF Value in v2: defaults, Customize, remembered choice (2026-10-08, JEG-471 v2 side / JEG-466 part 2)

Built on the engine's "Back-end contract: DDF Value" above. v2 still does no value math.

- **Series:** `ddf_value` is a first-class v2 series, with method "ddf", the ★ symbol and brand orange (#A84410 light, #F28C5B dark, at least 4.5:1). It sorts first everywhere, has its own "DDF Value" group in the table, and its chart line is drawn last and heavier (3.5 px).
- **Shown on/off:** whether DDF Value is shown is v2's own flag (`ddfShown`), because the composite has no engine toggle. `TradeValueV2.shown()` lists the shown series and `TradeValueV2.setShown(keys)` does what Customize's Done does; tests use both.
- **Default (first visit):** DDF Value plus every available as-published chart, ranked by DDF Value (`setLockOrder("ddf_value")`).
- **Customize:** the DDF Value group lists the engine's allowed inputs (`getCompositeInputs().allowed`), ticked where the engine uses them.
  - Only "not selected" inputs are selectable. A held, prior-week or unavailable source shows the engine's reason and is disabled (JEG-479: never a DDF input).
  - A missing DDF Value shows "—" with `row.ddfReason` when the engine gives one (JEG-479: fewer than two sources).
  - v2 reads `values.ddf_value` and never assumes which view it belongs to, so JEG-479's per-view DDF values need no change here.
  - On Done, a changed input set goes to `setCompositeInputs`.
  - Reset to default restores both the default shown set and `defaults`.
- **Remembered on this device (JEG-455 decision):** `localStorage["ddf.v2.selection"]` holds `{v: 1, shown, inputs (null = engine defaults), rank}`.
  - It is written on Customize Done and on a Rank by change, and read once at start-up, before a shared link is applied.
  - Storage errors are ignored, in which case the choice lasts the visit.
- **Reset** on Player values also restores Rank by to DDF Value (Jeremy, 2026-10-08).
- **Δ prior week for DDF Value:** `movers.deltaFor` uses the prior result's `currentValues` when present, so both sides cover the same inputs.
- **Copy:** the footer no longer says "no blended score". It now reads "DDF Value is our value, built from the inputs you choose in Customize. Every other series keeps its source's identity." Nothing explains the MR-17 methodology yet.
- **Tests:** `tests/test_v2_ddf_render.py` (test-unit), with 9 deliberately broken builds. The compare, offer, panels, states and waterfall tests now read the shown set from `TradeValueV2.shown()`, and widen it where a check needs several methods.

## Shared series picker, Risers by DDF Value, verdict by DDF Value (2026-10-08, JEG-466 / 465 / 467)

- **One picker (JEG-466).** `renderSeriesPicker(select, entries, selected)` in v2.js draws every per-tab
  series choice: Player values' Rank by (`#v2RankBy`), Risers & fallers' series (`#v2RSeries`) and Compare's
  Player values shown (`#v2CShown`). It is a native `<select>` (keyboard and screen-reader behaviour for
  free) with one `<optgroup>` per JEG-474 group in vocabulary order, DDF Value first: DDF Value,
  Projections, Trade charts (adjusted), Trade charts (as published), Value above waivers (Advanced).
  - Option label: symbol + the series in group words (`groupSeriesName`: "ESPN projection", "FantasyCalc
    chart (adjusted)", "FantasyCalc chart (as published)", "ESPN value above waivers").
  - A series on a prior week gets "· Wk N" in its label (the `priorWeekInfo` short text; the full sentence
    is the option's title).
  - A series that cannot be picked is listed disabled with its reason in the label ("— no prior week:
    …", "— not available for this league", "— waiting on fresh inputs").
  - 44 px tall on every tab (Compare's picker was 36 px).
- **Risers & fallers (JEG-465).** `movers.SERIES` starts with `ddf_value`; the tab opens on DDF Value
  whenever the engine has its prior week (`RISERS_DEFAULT`), else on the first series that has one.
  - DDF Value's Δ and its "before → now" are `getPriorWeek("ddf_value")` `currentValues − values`
    (`buildMovers` now reads "now" from `currentValues` too, not the row's value).
  - The meta line says "DDF Value · N of M sources have a prior week"; inputs the engine dropped from
    both weeks are listed with their reasons. The counts of players not compared stay.
  - Only the served week pair is offered for DDF Value (see BE-3).
  - Copy names every series in group words ("FantasyCalc chart (as published)", "Razzball projection").
- **Compare a trade (JEG-467).** "Player values shown" defaults to DDF Value (then the ranking series).
  - The verdict reads DDF Value whenever DDF Value is shown and available, whatever the picker says
    (`verdictSeries` in `collectCompare`). The picker drives the side cards' values and totals; the
    per-source table and its waterfalls show every series as before; the verdict card's waterfall is
    the verdict series'. With DDF Value not shown, the verdict reads the picked series (Jeremy, 2026-10-08:
    the verdict follows the picked series when DDF Value is hidden).
  - With a DDF Value missing for a player, the verdict says so and points to the table rather than
    to the picker.
  - The DDF Value row is first in "Difference by source & method", with a brand-orange edge, a bold
    name and the words "★ Decides the verdict".
- **Tests.** `test_v2_risers_render` (DDF movers equal the engine's `currentValues − values`; opens on
  DDF Value; grouped picker for Risers and Rank by, one series forced to "no prior week" is disabled
  with its reason; broken builds: picker ungrouped, Risers default not DDF). `test_v2_waterfall_render`
  (verdict = DDF Value net from engine values with the picker on another series; verdict-card waterfall
  = DDF Value's row; broken build: verdict follows the picker). `test_v2_compare_render` (DDF Value row
  first and marked; Values shown grouped and opening on DDF Value). `test_v2_offer_render` (side values
  follow the picker, DDF Value included). `test_v2_movers` (DDF "now" from `currentValues`).

## Trade targets: DDF Value as our value; tier follows the series (2026-10-08, JEG-455 / JEG-456 part 2)

- **Our value (JEG-455):** `TradeValueTargets.OUR_KEYS` is `ddf_value, espn, cbsros, razzball`; the default
  is DDF Value and the projections stay as choices. Each is one engine series read as is (targets.js does
  only the gap subtraction).
- **Source count:** with DDF Value, each row's Our value (table cell and phone card) carries "from N sources"
  (`row.ddfCount`; the tooltip names `row.ddfSources`). A player whose picked value is null cannot be a target;
  he is counted in "N players left out", now followed by the engine's reasons (`missingReason`), most common first.
  If a null ever reaches a row, the cell shows "—" with the reason.
- **Remembered on this device:** `localStorage["ddf.v2.targets"] = {v: 1, ours}`, written on change, read once at
  start; storage errors are ignored (the choice then lasts the visit).
- **Copy:** subtitle "We check four published trade charts against our values for your league. …" (headline
  unchanged). The footnote's "Our value is …" follows the pick: "the DDF Value, built from the inputs chosen in
  Customize on Player values", or "<projection> with Data Driven Adjustments".
- **Tier (Jeremy's ruling, everywhere in v2):** one helper, `tierFor(row, key, scope)` / `tierText(...)` in v2.js;
  `row.espnRole` is no longer read anywhere in app/v2.
  - `ddf_value` → `row.ddfTier`.
  - Any other series → the player's rank by that series within `scope.rows` against the engine's roster zones
    (rank < `starter_to_bench` = Starter, < `bench_to_waiver` = Bench, else Waiver). When the series is the engine's
    own ranking (Player values' Rank by), the rank is the row order (`fullRank`) and the zones are `getZones()`, exactly
    the chart's lines. Otherwise the zones come from the new read-only accessor `getZonesFor(key, pos)`. "—" when
    the series has no value for the player.
  - Player values (tooltip, Tier column, sub-line, drawer): Rank by. Trade targets (sub-lines, drawer opened from the
    tab): the tab's Our value, over the engine's rows at the current position. Compare a trade (player sub-line, drawer
    opened from it): the verdict series, over every priced player against the All-positions zones.
- **One-source DDF Value (Jeremy, 2026-10-08):** "Show the value it would be with one source if it's there, but flag
  the issue for the user." When the engine sets `row.ddfLowConfidence` (one input prices the player; `values.ddf_value`
  = that input, `ddfCount` 1, `ddfConfidenceNote`), v2 shows the value with the tag "◐ 1 source" (Jeremy, 2026-10-09: the engine's
  `ddfConfidenceNote` is the tooltip and part of the accessible name, "1 source: Only one source prices this player") everywhere the DDF Value appears: Trade targets (in place of "from N sources"; such players are targets),
  the Player values table and chart tooltip, the drawer hero and matrix, and Compare's player values and per-series
  lines. With 0 inputs the player is still left out and counted. Until the engine ships the flag, tests simulate it.
- **Native rank (JEG-482):** an opened Trade targets row shows "#N on <publisher>" per chart from
  `getNativeRank(playerKey, chart)` (the publisher's own order, before indexing). Not on phone cards (width).
- **Waiver-line test:** current data has no chart value at or below 0 (JEG-482 pure rescale), so the render suite
  simulates one (`SIMULATE_ROWS`) to keep the "0.0 · waiver line, no gap, never a buy" rule tested.
- **Engine accessor added (read-only):** `TradeValueCurveControls.getZonesFor(key, pos = current)` →
  `{starter_to_bench, bench_to_waiver}` (ordinal + 0.5, unclamped), the same roster ordinals `getZones()` uses for a
  non-composite ranking; `null` for `ddf_value` (use `ddfTier`). Needed because `getZones()` follows the engine's
  current ranking (DDF tier counts in a position view when ranked by DDF Value), which is not the Trade targets series.
- **Missing reasons (every tab):** `missingReason(key, row)` reads `row.missingReasons[key]` first (back end confirmed
  the field; not shipped yet), then `row.ddfReason` for DDF Value, then the generic line. Used by the Player values
  table and chart tooltip, the drawer hero and matrix, and Compare's player values. A finite 0 always shows "0.0".
- **Tests:** tests/test_v2_targets.py (DDF default, ESPN alternative, one-source player kept; broken builds: default reverted to ESPN, DDF
  Value dropped from the choices). tests/test_v2_targets_render.py (Our value = engine `ddf_value`, "from N sources" =
  `ddfCount`, tier = `ddfTier`; ESPN / CBS / Razzball through the picker with the tier from that series' rank; pick
  remembered after a reload; broken builds: default reverted to ESPN, tier from espnRole, source count missing, pick
  not remembered). tests/test_v2_ddf_render.py (Player values tier ranked by DDF Value and by one other series; a
  simulated `missingReasons` entry shows "—" with that reason and a finite 0 shows "0.0"; broken builds: tier from
  espnRole, engine reason ignored). test_below_leg_zero_render and test_espn_zero_badge_render now pick ESPN
  explicitly (they test the ESPN-0 rule).

## Player values: expand, Reset zoom, filter chips (JEG-483, 2026-10-08)

Restores usability the above-the-fold pass (JEG-470) compressed; that layout stays. Supersedes "Reset zoom
removed" and the small "Set exact values" link in the JEG-470/472/473/475 section above.

- **Expand chart (⤢).** A 44 px button in the plot corner, in the `.v2-zoom` group. It opens `#v2Expand`: a large
  dialog over a dimmed page on desktop (scrim, ✕, Esc, focus kept inside, focus back on ⤢ when closed), full screen
  below 768 px. The live `#v2Plot` node moves into the dialog and back on close (a placeholder holds its height), so
  there is one chart, one pair of brushes and one state: a brush or zoom there is the toolbar's Show, the table's
  rows and the chart card's chart. Inside: a ~75vh plot with both brushes (the Y brush shows at 390 too), quick
  Top 25 / 50 / 100 / All buttons that set Show, "Y axis fits the value range" (on by default; the Y brush also
  rescales the Y axis there and lines outside it are clipped, never clamped) and the legend. `renderCharts()` runs on
  open, close and resize; the chart sizes from its container.
- **Player names when zoomed.** Kept on the main chart (names under each point once points are 64 px apart). The
  expanded chart staggers names on two lines, so it names players from 34 px apart (Top 25 at 1440 names all 25).
- **Expand table.** "⤢ Expand" in the table card head moves `#v2TableWrap` into the same dialog at full height.
  Pos / Team / Tier are their own sortable columns there (Tier sorts Starter, Bench, Waiver); sticky header,
  heat tint and Show more paging are unchanged because it is the same table.
- **Tier** in the expanded table uses the one v2 helper, `tierFor` / `tierText` (Trade targets), like every tab; it
  sorts Starter, Bench, Waiver, then —. The "◐ 1 source" tag shows in the expanded table and the expanded chart's
  hover card because they are the main table and chart.
- **Reset zoom.** In the plot corner, shown only while Show is Custom from a zoom, brush or exact ranks. The Show
  preset in force before the zoom is remembered (`state.zoomFrom`); Reset zoom clears the rank-window zoom and the
  value range and returns to that preset. Search, position, sort, Δ and Rank by stay. The toolbar Reset is unchanged.
  `state.rankZoom` records whether the rank window itself was zoomed; a Custom that came only from the value range
  uses the remembered preset's rank window, and clearing the range returns Show to that preset.
- **Filter chips.** Under the toolbar, one chip per active filter: "Value 12–30 ✕", "Ranks 20–60 ✕",
  "Search: jsn ✕", "Position: WR ✕". Each clears only its own filter (the ranks chip keeps the value range and
  vice versa). 32 px visual, 44 px hit area.
- **Set exact values** is now a 44 px, 13 px-text button at the end of the chart card's title line (it was a 10 px
  link under the Y brush).
- **Tests:** `tests/test_v2_expand_render.py` (test-unit), with 9 deliberately broken builds. `test_v2_panels_render`
  now allows ⤢ and Reset zoom inside the chart.
- **Jeremy's answers (2026-10-09):** Reset zoom clears both brushes; "Y axis fits the value range" is on by default;
  "Set exact values" stays on the chart card's title line; Tier follows the ranking series on every tab (done with
  `tierFor` / `tierText`; this branch's own `tierOf` was dropped). The Y axis
  is never capped at a fixed value: it scales from the largest value shown (indexed values can exceed 70).

## Manifesto tab (Jeremy, 2026-10-09)

- **What:** Jeremy's "Fantasy Football Manifesto" as a long-form page at `#manifesto`, first in the nav ("Manifesto"). The landing tab stays Trade targets; Manifesto is only first in nav order.
- **Text:** in `app/v2/shell.html` (`#v2Manifesto`), verbatim from his Google Doc "Fantasy Football Manifesto V2" (read 2026-10-09). Only the HTML structure is ours: h1 = the doc title, 12 numbered h2 sections, paragraphs, bold, lists. Do not edit his sentences; replace the whole text from the doc when he revises it.
- **Brand:** a small "Data Driven Football" eyebrow above the h1.
- **Plain text only (Jeremy, 2026-10-09: "Why does manifesto need so many controls. Its text."):** no contents list, no links to the tool, no buttons. A first build had both; they were removed before shipping.
- **Chrome:** the league bar and the Showing bar are hidden on this tab (no values on it). The nav freshness label still updates.
- **No engine needed:** the page shows as soon as the script runs, without the loading card, and still shows if the engine fails (`applyStatic()` in v2.js).
- **Layout:** one 70ch text column, 17 px / 1.7 (16 px / 1.65 below 768 px), v2 tokens and Inter. No horizontal scroll at 390 px; the six short tab labels still fit on one row.
- **Tests:** `tests/test_v2_manifesto_render.py` (test-unit), with 4 deliberately broken builds (section 7 dropped, Manifesto not first, a link added to the text, Manifesto as landing). It also checks the tab has no links, buttons or form controls. `test_v2_nav_render` checks Manifesto is first; `test_v2_a11y_render` includes the tab in its contrast sweep.

## Feature contract test (JEG-506, 2026-10-09)

The contract is Jeremy's Google Doc "Data Driven Football: feature contract"
(https://docs.google.com/document/d/1UDRlVTdOiAdI6gSSklxwB-R9uINozVmIILMwbvCBiH0). The Doc is the source of truth.

Workflow rule (Jeremy):
- A change that breaks a contract line doesn't ship.
- Changing or removing a line needs Jeremy's yes, recorded in the Doc. Then re-export the Doc and regenerate the mirror; never edit the mirror to change the contract.

How it works:
- `docs/feature-contract.md` mirrors the Doc. Regenerate it with `python scripts/sync_feature_contract.py <exported text>` (a file or `-` for stdin). CI has no Google auth, so the script only cleans text you export (Drive connector or File > Download > Markdown) and adds the header.
- `tests/test_v2_contract_render.py`:
  - `CHECKS` maps every ID in the mirror to a check function, or to `PENDING("JEG-xxx")` for a line marked "to build: JEG-xxx". A pending entry may carry a partial check of what already exists (GL-17 for Player values).
  - The unit test (`ContractMirrorTest`, no browser) fails when a mirror ID has no entry, when CHECKS has an ID the Doc dropped, when a "to build" line has a live check or the wrong ticket, or when a live line is still pending. `WORDING_HOLDS` is the only exception: TT-05 is held on JEG-510 until "indexed" becomes "rescaled".
  - `SUBPART_HOLDS` lists part of a live line that is not built yet. GL-11's "Edit league is the primary control" is held on JEG-498, because no primary styling exists yet. GL-11 still checks that #v2EditLeague and #v2Weights exist, found by ID rather than label ("Weights & bench" becomes "Position weights" in JEG-537). It also checks that league edits stay a draft until Apply. The mirror test fails if the held wording leaves the Doc line.
  - The render test does one page load per scenario (Player values with two reloads, the other tabs in one page including a shared Compare trade, 390 px across all tabs, engine failure), then runs every live check against those snapshots. About a minute on this machine.
  - Checks are presence plus basic behaviour. Deep correctness stays in the other `test_v2_*` suites; GL-02 checks one engine value per tab.
  - Fixtures, so checks never pass vacuously: the freshness file is fixed (current, prior week, unknown, not updating), and every fifth priced player is flagged one-source in what `getRows` / `getAllRows` return (Week 5 has no one-source players, so GL-03 / TT-08 would otherwise see no "◐ 1 source" tag). Values are untouched.
  - `test_guard_fails_on_broken_builds` serves broken v2.js / v2.css / shell.html through page routes and requires the named check to report a real finding for each fault (13 faults over 11 IDs, three grouped runs).
- When a ticket ships a pending line: Jeremy drops "to build" in the Doc, the mirror is regenerated, the mirror test fails, and the shipping ticket replaces `PENDING` with a real check.

## Back-end contract: bench share readout and league weeks (JEG-536, 2026-10-09)

Engine side of `es-value-001` (docs/methodology.md ES-14, rulings ES-15). The front end (JEG-537)
builds the readout and the settings against this. All on `window.TradeValueCurveControls`.

**Readout.** `getBenchShareReadout()` returns, or `null` before the first build or with no projection
included:

```
{QB, RB, WR, TE, overall,   // fractions (0.091 = 9.1%): the bench tier's share of each position's
                            // DDF Value, and of the whole pie
 override: false|true,      // true when the reader's override is on
 overrideValue: null|number,// the override (0.01-0.30) when on
 fillInShare: number,       // the pie paid on the bench groups (diagnostic, not the headline)
 method: "expected-starts"  // or "fixed-share" if the parameters file failed to load (then 15% slices)
 contentWeek, window: [first, last], error: null|string}
```

Copy: "Bench share this week: QB x%, RB y%, WR z%, TE w%, from your league settings"; when
`override` is true, "Bench share: x% (your override)" with x = `overrideValue`, and a reset link that
calls `setBenchShareOverride(null)`. Week 5, 12-team Full PPR, defaults: QB 22.4%, RB 8.4%, WR 7.5%,
TE 12.8%, overall 9.2%.

`getBenchShare()` keeps its name and now returns the share in effect: the override when on, else
`overall`. It is no longer 0.15 by default.

**Settings.** Each setter re-prices and publishes (`trade-value-shared-change`, whose detail now
carries `benchShareOverride` and `lineupSettings`) unless `publish` is `false`. An invalid value
throws a `RangeError` and leaves the settings unchanged. Each setter returns the settings in effect.

| Setting | Getter | Setter | Default | Values |
| --- | --- | --- | --- | --- |
| Last regular-season week, playoff weeks | `getLeagueWeeks()` → `{regularSeasonEnd, playoffWeeks: [first, last]}` | `setLeagueWeeks({regularSeasonEnd, playoffWeeks}, publish?)` | `14`, `[15, 17]` | weeks 1-18; playoffs start after the regular season; first ≤ last |
| Optimize for | `getOptimizeFor()` | `setOptimizeFor(value, publish?)` | `"season"` | `"season"` (whole season), `"regular"`, `"playoffs"` |
| Injury history (Advanced) | `getInjuryHistory()` | `setInjuryHistory(value, publish?)` | `"recent"` | `"recent"` (recent seasons, five-season half-life), `"all"` (all seasons equally) |
| Projection confidence (Advanced) | `getProjectionConfidence()` | `setProjectionConfidence(value, publish?)` | `1` | `1.5` = Less, `1` = As measured, `0.5` = More (it multiplies the uncertainty) |
| Bench-share override (Advanced) | `getBenchShareOverride()` → `null` or number | `setBenchShareOverride(value \| null, publish?)` | `null` (off) | 0.01-0.30, clamped; `null` turns it off |

Bulk: `getLineupSettings()` → `{regularSeasonEnd, playoffWeeks, optimizeFor, injuryHistory,
projectionConfidence, benchShareOverride}`; `setLineupSettings(partial, publish?)` takes any subset of
those keys (one re-price); `getLineupSettingsDefaults()` → the same shape at the defaults (from
`config/lineup_parameters.json`). `getLineupParameters()` → the resolved parameters in use
(`{objective, injury_history, league_weeks, content_week, projection_confidence, window, bye,
horizon_weeks, positions: {pos: {m, sigma_rel, sigma_floor}}}`), for the info text or the inspector.

`setBenchShareFraction(x)` (the old slider) now sets the override; `setBenchShare(pct)` likewise.

**Rows.** `getRows()` / `getAllRows()` / `getPlayer()` rows gain `lineupShare` (expected share of his
value above waivers that reaches a lineup, 0-1) and `startWorthy` (probability his level sits above
the starter line, 0-1), both null without lineup parameters. Drawer copy: "expected lineup share".

**Diagnostics.** `TradeValueCurveDiagnostics.valuePipeline` gains `method`, `benchShare` (the readout
object above, replacing the number), `benchShareInput`, `benchShareOverride`, `lineup`, `chartSigma`,
and per source and position `avail`, `bands: [{depth, lo, hi, fill}]` and `lineup: {m, unavailable,
nPerTeam, sigmaRel, sigmaFloor}` next to `waiver` and `starterLine`. `benchShareApplied` stays the
number (the pie on the bench groups).

**Share links (front end owns them).** Carry every setting; write a key only when it differs from
`getLineupSettingsDefaults()`, read it back through `setLineupSettings` before `refresh()`:

| Key | Value | Example |
| --- | --- | --- |
| `rs` | last regular-season week | `rs=13` |
| `po` | playoff weeks, first-last | `po=14-16` |
| `opt` | `season` / `regular` / `playoffs` | `opt=playoffs` |
| `inj` | `recent` / `all` | `inj=all` |
| `conf` | `0.5` / `1` / `1.5` | `conf=1.5` |
| `bso` | override, 3 decimals; absent = off | `bso=0.120` |

The existing `bench=` key should stop being written (it was the 15% slider). Reading an older link:
`bench=0.150` (the old default) means no override; any other `bench=` value without `bso=` is the
sender's override.
