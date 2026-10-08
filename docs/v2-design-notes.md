# v2 front end: design source and build notes

Figma file: https://www.figma.com/design/fCffo4EdZgUBkoVb7cQdr3/Trade-Dashboard-v2---Design-Review
(page "V3 · Resolved design & handoff"). The file opens without signing in. The Figma connector is
on the Starter plan and runs out of calls quickly, so these notes record what was read from the
canvas on 2026-10-07.

## Frame map (open with `?node-id=<id>`)

| Frame | Node |
| --- | --- |
| 00 Start here | 59-2938 |
| 01 Player values, desktop 1440 | 59-2077 |
| 02 Player values, mobile 390 | 59-2443 |
| 03 Market disagreement, desktop 1440 | 59-1817 |
| 04 Market disagreement, mobile 390 | 59-2567 |
| 09 Source selection overlay | 54-957 |
| 10 Freshness overlay | 54-1028 |
| 11 Weights & bench overlay | 54-1128 |
| 12 League settings overlay | 54-1173 |
| 13 Player detail, desktop drawer | 59-2259 |
| 15 How values work, desktop | 59-2316 |
| 17 Design system & responsive rules | 59-1484 |
| 18 Empty, loading & failure states | 59-1668 |
| 19 Implementation contract | 59-1575 |
| 22 Review amendments: interactions & source logic | 61-1593 |
| 24 Navigator, filters & trade detail states | 68-147 |

Not yet mapped: 05/06 Risers & fallers, 07/08 Compare a trade,
14 Player detail mobile, 16 How values work mobile, 20 Source selection mobile, 21 Chart options,
23 Benchmark decisions.

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
