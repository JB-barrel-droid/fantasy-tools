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

- Our value = one engine projection-derived DDF series, picked in "Our value" (Jeremy,
  2026-10-07): `espn` (ESPN, default), `cbsros` (CBS rest-of-season) or `razzball`. One series at a
  time, never a blend. A series unavailable at the current setting is listed disabled with its
  reason; if the picked one becomes unavailable the tab fails closed rather than swapping. The pick
  is v2 module state, so it survives switching tabs (no storage, like the other v2 selections).
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
- Default charts: available, current-week ones. Older-week charts are listed as not compared until
  "Include older-week charts" is ticked. Position is the engine's shared setting, so it carries
  across tabs.
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
  - Indexed view only. In the other views the result is `available: false` with the reason.
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
