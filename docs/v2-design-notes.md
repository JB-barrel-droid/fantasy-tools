# v2 front end: design source and build notes

Last updated: 2026-10-23 (JEG-975: merged PRs and Done tickets no longer described as open; seven tabs; roster paste wired; phone menu). Where a dated section below disagrees with the "Nav structure" section, the later section governs.

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

The 2026-10-08 review gap lists, polish passes, page-weight measurements and multi-device sweep are archived in `archive/2026-10-15-docs/v2-design-notes-build-log.md`. Current behavior is specified below and by `docs/feature-contract.md`.

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

**BE-5 · Stale team on players no source prices (JEG-502, 2026-10-09).** In
`data/fixtures/current/players.json`, 29 of 306 `universe_only` players have a `team` that disagrees
with the team in their own `unpriced_reason`, which comes from the current Sleeper roster. For example,
Scott Miller has `team` PIT, but his reason says "Practice squad (CHI)"; Phillip Dorsett has ATL
but "Practice squad (LV)". Free agents also keep an old team. v2 shows only the position and the
reason for these players until `team` follows the roster status (free agent = no team).

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
  **JEG-1044 (2026-10-24): the DDF blend became the value basis.** `setBasis(config, publish = true)` /
  `getBasis()` / `resetBasis()` replace the Customize DDF blend tab (removed; v2 keeps `setCompositeInputs`
  only as an alias for an equal-weight projection blend). `config`: `null`, `"default"` or `{mode:
  "default"}` (our methodology); `{mode: "single", source}`; `{mode: "blend", sources?, weights: {key:
  1-100}}` over the seven pipeline sources. `getBasis()` → `{mode, isDefault, source, sources, weights,
  percents (sum 100), label ("FantasyCalc", "60% ESPN + 40% Razzball"), shortLabel, rescaledLabel
  ("Rescaled (to FantasyCalc)"), applied, members, fellBackToDefault, sourceStates: [{key, label, family,
  usable, reason}]}`. It drives `ddf_value` only (blended), the Indexed basis, tiers and ranking; the
  trade chart average and `ddf_value_projections` ignore it; the prior week is run on it. The shared-state
  event detail carries `basis`. `value_check compare --basis '<json>'` runs page and reference under one.
  The reader's basis and player overrides are one record in localStorage `ddf-v2-value-overrides` (v2:
  `{v, basis, values, names}`; v1 = values and names only; the retired `ddf.v2.selection.inputs` migrates
  in once). `window.DDFOverrides` (app/v2/overrides.js) owns the tab, the "Overrides active" bar, the
  share-link parameters (`basis=`, `ov=`) and the banner; other tabs read rows and need nothing else, and a
  consumer that re-runs on league changes listens for `ddf:league-settings-changed` (reason `sources` for a
  basis change, `overrides` for a player value).
- **JEG-1058 / JEG-1059 (2026-10-26): an override is a value or an adjustment, and an overridden value
  is flagged everywhere it shows.** `getValueOverrides()` → `{player_key: 58.0}` for an absolute
  override, `{player_key: {type: "adjustment", delta: 5}}` for an adjustment (the pipeline's own value
  plus the delta, clamped to the 0-100 value scale; an override that arrives from outside the editor —
  a link, an import, a saved record — is put on the same scale). A row carries `valueOverride` (the effective
  value the reader sees), `ddfPipelineValue` (the pipeline's value before the overlay) and
  `valueOverrideSpec` (what the reader set: `{type, value}` or `{type, delta}`). `window.DDFOverrides.flag(row)` returns the badge element
  (`.v2-ov-flag`; `title` and `aria-label` are "You set this player's value to 58.0 (was 53.0 from DDF
  Value). Reset on the Overrides tab."), and every view that shows an overridden DDF Value appends it
  (Player values, Trade targets, Compare a trade, Find a trade, Waivers, the workspace opportunities
  table, the Overrides tab). The share link carries `ov=key:+5` (a sign, or the space `+` decodes to,
  means an adjustment) and the export file carries `type: "adjustment", delta`.
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
  "players left out" note moved below the lists. At 1440 × 900 and 1366 × 768 the H1 and subtitle are
  above the fold; the top 5 of both lists end by 1080 px (JEG-675 proposed 1060 on 2026-10-17; Jeremy accepted 1080 px on 2026-10-23, JEG-877 option B. The rows are two-line since #639, so the old "top 5 above a 768/900 px fold" no longer holds;
  measured 1058.5 px at 1440 × 900 and 1055.5 px at 1366 × 768 on the pinned-holds fixture when 1060 was proposed, and 1073.8 px at 1366 × 768 on the 2026-10-22 fixture).
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
- **Bench share shown is the share used.** (Superseded 2026-10-10 by JEG-508: no feasible windows any more; see "After JEG-508" below.) Below a position's feasible window the engine prices at a higher share
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

## Manifesto tab (Jeremy, 2026-10-09; route superseded by the Writing tab, JEG-855, 2026-10-22)

- **What:** Jeremy's "Fantasy Football Manifesto" as a long-form page at `#manifesto`, first in the nav ("Manifesto"). The landing tab stays Trade targets; Manifesto is only first in nav order.
- **Text:** in `app/v2/shell.html` (`#v2Manifesto`), verbatim from his Google Doc "Fantasy Football Manifesto V2" (read 2026-10-09). Only the HTML structure is ours: h1 = the doc title, 12 numbered h2 sections, paragraphs, bold, lists. Do not edit his sentences; replace the whole text from the doc when he revises it.
- **Brand:** a small "Data Driven Football" eyebrow above the h1.
- **Plain text only (Jeremy, 2026-10-09: "Why does manifesto need so many controls. Its text."):** no contents list, no links to the tool, no buttons. A first build had both; they were removed before shipping.
- **Chrome:** the league bar and the Showing bar are hidden on this tab (no values on it). The nav freshness label still updates.
- **No engine needed:** the page shows as soon as the script runs, without the loading card, and still shows if the engine fails (`applyStatic()` in v2.js).
- **Layout:** one 70ch text column, 17 px / 1.7 (16 px / 1.65 below 768 px), v2 tokens and Inter. No horizontal scroll at 390 px; the tab row fits on one row at tablet width and up (phones use the menu, JEG-953).
- **Tests:** `tests/test_v2_manifesto_render.py` (test-unit), with 4 deliberately broken builds (section 7 dropped, Manifesto not first, a link added to the text, Manifesto as landing). It also checks the tab has no links, buttons or form controls. `test_v2_nav_render` checks Manifesto is first; `test_v2_a11y_render` includes the tab in its contrast sweep.

## Feature contract test (JEG-506, 2026-10-09; contract v1.2 2026-10-10)

The contract is Jeremy's Google Doc "Data Driven Football: feature contract" v1.2
(https://docs.google.com/document/d/1mI2vo4R74Fp-x14yR7ggh0T3WdcD6xjciLv7gVh4iJo; v1.1 was a different Doc). The Doc is the source of truth.

Workflow rule (Jeremy):
- A change that breaks a contract line doesn't ship.
- Changing or removing a line needs Jeremy's yes, recorded in the Doc. Then re-export the Doc and regenerate the mirror. Never edit a mirror to change the contract.

How it works:
- Two mirrors, both written by `scripts/sync_feature_contract.py` from text you export (Drive connector or File > Download > Markdown). CI has no Google auth, so the script only cleans that text and adds the header.
  - `docs/feature-contract.md` mirrors the contract: `python scripts/sync_feature_contract.py <export>`. A new contract version in a new Doc means updating `DOCS["contract"]["url"]` in the script.
  - `docs/manifesto-mirror.md` mirrors Jeremy's Manifesto Doc ("Fantasy Football Manifesto V2"): `python scripts/sync_feature_contract.py --doc manifesto <export>`.
  - `docs/manifesto.md` is not used. It carries a repo-written terminology note, so it is not a copy of the Doc.
- `tests/test_v2_contract_render.py`:
  - `CHECKS` maps every ID in the mirror to a check function, or to `PENDING("JEG-xxx")` for a line marked "to build: JEG-xxx". A pending entry may carry a partial check of what already exists: TT-05's ⓘ until JEG-510 (GL-17 and GL-18 went live with JEG-500).
  - A line's "to build" counts anywhere in its block, from its ID to the next ID or heading. GL-24 has it on a later paragraph.
  - The unit test (`ContractMirrorTest`, no browser) fails in four cases:
    - a mirror ID has no entry;
    - CHECKS has an ID the Doc dropped;
    - a "to build" line has a live check or the wrong ticket;
    - a live line is still pending.
  - The render test does one page load per scenario, then runs every live check against those snapshots:
    - Player values, with two reloads;
    - the other tabs in one page, including a shared Compare trade;
    - 390 px across all tabs;
    - engine failure.
  - Checks are presence plus basic behaviour; deep correctness stays in the other `test_v2_*` suites.
    - GL-02 checks one engine value per tab.
    - GL-11 (v1.2) is draft-until-Apply only, found by #v2EditLeague. "Edit league is primary" became GL-22 (JEG-498).
    - MF-01 compares the rendered Manifesto with `docs/manifesto-mirror.md` word for word, ignoring Markdown marks, and checks that it has no links or controls.
    - TT-06 checks the "Wk N" badge on the Trade targets headers, the Player values legend and table headers, and the Compare rows.
  - Fixtures keep the checks from passing vacuously. Values are untouched in all three.
    - The freshness file is fixed: current, prior week, unknown and not updating.
    - Every fifth priced player is flagged one-source in `getRows` / `getAllRows`, so the ◐ checks (GL-03, TT-08) can always fail.
    - USA Today is served one week behind through `getSourceInfo` and `getSourceFreshness`, so TT-06 always has a badge to check. It is switched off for the all-current reload in GL-05.
  - `test_guard_fails_on_broken_builds` serves broken v2.js / v2.css / shell.html through page routes. It requires the named check to report a real finding for each fault: 15 faults over 12 IDs.
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

- TT-06 UI change (v1.2): the Player values table header and the Compare row now use the shared "Wk N" badge for a chart a week behind. Before, they showed "· Week N" / "Week N · older week" text.

## After JEG-508: estimated values, bench share, hermetic missing values (JEG-541, 2026-10-10)

The JEG-508 engine (PR #491) changed the v2 contract (GAP-508-V2-CONTRACT, JEG-537 comments). What v2 does now:

- **Estimated values (VP-11).** The engine marks every chart value it filled in for a rosterable player the chart
  doesn't list: `row.estimated = {seriesKey: reason}` (both the chart key and its `*_adjusted` alias carry it).
  Wherever v2 shows that value it adds "≈ estimated" (symbol and word) with the engine's reason as the tooltip
  and accessible name: Player values table cells, the chart tooltip (reason also shown as text), the player
  detail's value and method matrix (reason also shown under the value), Compare a trade's per-player lines and
  Trade targets' chart cells. Estimated values are drawn like listed ones. One helper (`appendLowConfidence`)
  adds both the "◐ 1 source" and the "≈ estimated" tags, so every value site gets both.
  Test: `tests.test_v2_estimated_render`.
- **Bench share.** The two-tier calibration and its per-position feasible windows are retired (VP-10).
  `getBenchShareUsed(share)` returns one share for all positions: the share itself, 0 when no source has bench
  players above waivers, 1 when none has starters above waivers, null before the values are built.
  `getBenchBounds()` is the fixed slider range `[0.01, 0.30]`. v2 still shows the used share, never the request:
  - the panel says "Range 1.0%–30.0% · Recommended 15%" (it said "Feasible … for this league" and "Feasible
    bounds recalculate with league structure", both false now);
  - at 0 or 1 the note reads "Bench x% requested · priced at 0.0% (no source has bench players above waivers)";
  - with no used share it shows "—" with "Bench share not available: the values are not built yet", never the
    requested share.
  The JEG-536 readout (`getBenchShareReadout()`) is not on main yet; JEG-537 builds the readout UI against it.
- **Missing chart values.** After JEG-508 every chart prices every player at a position it prices (listed,
  estimated, or 0 below rosterable depth), so a chart is null only when the engine says why (e.g. "Not enough
  shared players to index"). Trade targets now shows the engine's `missingReasons[chart]` before its generic
  "Not on X's chart".
- **Tests no longer depend on live gaps.** The compare, offer, targets and waterfall render suites simulate the
  condition they check by wrapping the engine's row accessors in the page (a player missing one series with a
  reason; a projection that disagrees with DDF Value), so each deliberately broken build still fails whatever
  this week's data looks like.
- **How values work** puts the engine's waiver note ("estimated players at RB (4) …") in a `data-engine` node, like
  the league card: its counts are the engine's, and the copy rule (no numbers outside engine nodes) still holds.

Still on the old contract (front-end follow-up, GAP-508-V2-CONTRACT): v2 groups the deprecated
`*_adjusted` aliases as "Trade charts (adjusted)" and its tests toggle them. The aliases carry each chart's
Adjusted values, so the numbers are right, but the engine wants v2 to read the chart keys in the Adjusted tab and
drop the alias group before it removes them.

## Module cards: expand and collapse (JEG-500)

`app/v2/modules.js` (loaded before v2.js, no engine code, no edits inside v2.js) gives every data card a
44 px chevron (`aria-expanded`) and an expand control. Collapsed, a card keeps its head and shows one summary
line read from the card's own text (e.g. "Sell: 230 of 738 players ..."); the rest is hidden. Collapsed cards are
remembered in `localStorage` key `ddf.v2.modules` (`{v: 1, collapsed: {headingId: true}}`). Expand: the
chart and table on Player values reuse their JEG-483 full-screen dialog; every other card spans its grid row
and drops inner scroll caps (`aria-pressed`, not remembered). To cover a new card, add one entry to `CARDS` in
modules.js. How values work and Manifesto are reading pages and are not modules. Tests:
`tests/test_v2_modules_render.py` (all four data tabs, reload, 6 broken builds) and GL-17 / GL-18 in the contract test.

## Trade targets: market average beside Our value (JEG-504, 2026-10-12; contract TT-09)

- `marketAverage(ours, cells)` in `app/v2/targets.js` gives each target player `market = {value, count, left, diff, equal}`:
  the mean of the compared charts' rescaled values that price the player (a finite 0 counts; a null is left out and
  counted in `left`), `diff` = our value minus the mean. It follows the "Compare against" picker (`used`).
- Display (`marketValue` in v2.js): a "Market average" column after Our value in the table, a "Market avg" run on phone
  cards. Shows the average, "avg of N" (plus "· K left out"), and "▲ +1.2" / "▼ −1.2" (symbol + sign; ▲ = our value is higher).
  When the average equals our value to one decimal the cell shows only "= market average", with no number or difference.
  No chart prices the player: "—" with a reason.
- Tests: `tests/test_v2_targets.py` (recomputation, with mutations) and `tests/test_v2_targets_render.py` (`check_market`).

## Trade targets: Check 1 market consensus (JEG-677, 2026-10-16; contract TT-03 / TT-04)

- `marketConsensus(ours, cells)` in `app/v2/targets.js` replaces the mean (`marketAverage`): `market = {value, count, of, left,
  diff, gap, equal, side, agree, eligible, dots}`. `value` is the median of the compared charts that price the player (a finite
  0 counts), `gap` = consensus minus our value. `eligible` needs 2+ priced charts, a consensus above the waiver line (0) and a
  strict majority (`agree * 2 > of`) on the consensus's side of our value. Sell lists gap > 0, Buy gap < 0.
- JEG-820 (2026-10-22, ticket option B, per standing instruction): `market.weight = min(ours, value)` and
  `market.score = |gap| x weight`; both lists sort by `score` descending (engine order breaks ties), and Sell drops
  players with `ours < SELL_FLOOR` (5), counted in `belowSellFloor` and said in the footnote. Before: raw gap put
  0.0 to 3.4 bench players at the top of Sell (Boston 1.2 vs 14.6, Corum 0.0 "Drop"). After (Full PPR 12, 2 charts):
  Skattebo 9.5 vs 13.0, Mason 9.6 vs 13.1, Hampton 9.3 vs 12.8, Marks 10.6 vs 13.7, Etienne 9.4 vs 12.7.
  Buy is unchanged in substance (Gibbs, JSN, Nacua, Bijan, Walker ...): ours / consensus is 1.3 to 1.5 in every
  consensus bucket, so the Buy side is our steeper scale, not per-player mispricing (`docs/math-review-agenda.md`
  MR-28). The footnote also says when DDF Value rests on one source for a listed player (leads, not verdicts).
- JEG-833 (2026-10-22, proceeding per standing instruction): Buy compares at the charts' rank. `rankEquivalents` in
  targets.js gives every player with a 2+ chart consensus `market.marketRank`, `ourRank`, `oursAtRank` (our value at
  the charts' rank, same position, same compared players), `rankGap = oursAtRank - ours` and
  `buyScore = |rankGap| x min(ours, consensus)`. Buy lists `rankGap <= -BUY_RANK_MARGIN` (2) by `buyScore`; the rest of
  the "market pays less" players are `scaleOnly` (+ `scaleOnlyNames`, by ours) and get a footnote. A monotone rescale
  gives rankGap 0 everywhere, which is why the ticket's options A (position share), B (ceiling) and C (percentage)
  all failed on the live data: with 3 charts at Full PPR 12 the share gap still put Smith-Njigba -35%, Nacua -33%,
  Chase -31%, Walker -27%, Gibbs -21% on top; by rank the top five are all 0.0. After: McCaffrey (charts RB8, we RB5,
  -6.4), Hubbard (RB12 vs RB10, -5.0), Breece Hall (RB18 vs RB17, -4.1), Jefferson (WR9 vs WR6, -2.9), Judkins, Goff,
  Mahomes, Adams; the same names lead every one of the 12 setups. Display: Buy's big number is `rankGap`, the column
  reads "Gap at chart rank", each table row carries an inline `.t-score` run "score 32" (rounded, 10 px; Sell "score 49") with
  the ranks in its tooltip and `data-market-rank` / `data-our-rank` (a longer run squeezed the player column and pushed
  the top 5 under the JEG-675 fold), and each phone card prints "RB8→RB5 · score 32.1", the meta line reads "ranked by gap × value at stake, biggest score first", and the market
  cell's ▲ / ▼ line is "3.3 above" / "3.3 below" (phone QA round 2: the signed number read as a contradicting gap).
  `buildTargets(rows, charts, {keep})` takes every row and filters with `keep` after the ranks, so a name search
  cannot change a player's rank.
- Default Our value is DDF Value (`ddf_value`, first in `OUR_KEYS`; Jeremy 2026-10-16 reversed the first JEG-677 DDF Projections default). Chart values are the engine's Indexed series; dots carry them.
- Display (v2.js `targetBest` / `agreeNode`): "Market consensus" column ("median of N"), "Gap vs consensus" column with
  "N of M charts agree" and one dot per chart (above / below our value). Per-chart cells keep their own gaps.
- Decision: Jeremy confirmed 2026-10-16 that the default stays DDF Value (JEG-455); the first JEG-677 pass reversed it and was corrected. An
  ESPN-0 player now lists only when most compared charts pay for him (a chart at its waiver line counts as pricing him at 0).

## Compare a trade: headline answers with confidence (JEG-505, 2026-10-12; contract CT-02)

Two plain lines open the verdict card (`TradeValueTrade.tradeHeadlines`, rendered by `renderHeadlines`); the existing
verdict, waterfall and story stay below. Each line is an answer (symbol + word) and a confidence (dots + word); a
second muted line gives the reasons.

1. **"Should you propose or accept?"** by DDF Value (the verdict series): Yes (▲) / No (▼) / Even (=), or "Not yet" when a
   DDF value is missing. Agreement = share of the other complete series (same set as the verdict) on the same side.
2. **"Will they accept?"** from the published charts only (as-published series, method `indexed`): the share of complete
   charts on which the other manager wins or breaks even (our net <= 0 as shown). Likely (▲) at 2/3 or more, Unlikely (▼)
   at 1/3 or less, otherwise Toss-up (≈). Agreement = share on the answer's side (Toss-up: the larger side).

Confidence rules (High / Medium / Low):
- agreement 75% or more = High, 60% or more = Medium, else Low;
- fewer than 3 sources (line 2: charts; line 1: other series) caps at Medium; no other source at all reads Medium;
- **thin margin:** DDF net under 5% of the value traded (give + receive, DDF series) reads Low on both lines even when every
  source agrees. Jeremy, 2026-10-09 (JEG-505 comment); the ticket had proposed 3%;
- a one-source (low-confidence) DDF Value in the trade lowers line 1 by one level (line 2 does not read DDF).
Tests: `tests/test_v2_headlines.py` (constructed trades recomputed from raw values, with mutations) and the headline check in
`tests/test_v2_compare_render.py`.

## Find a trade is its own tab (JEG-852, 2026-10-22)

Jeremy: "Make it so finding a trade is a separate tab from discovering a trade."
- The finder (`app/v2/finder.js`: your roster, their roster, package size, Keep starting lineup filled, Find trades, results) moved out
  of Compare a trade into its own page `#v2FindTrade`, tab "Find a trade" (`v2/#find-trade`, view `find`), directly after Compare a trade.
  Compare a trade is now only for a trade you already have in mind: Build a better offer, Verdict, Difference by source.
- Old `#compare-trade` links and shared trade links (`#compare-trade?give=..&get=..`) are unchanged. Each finder result still links to
  `v2/#compare-trade?give=..&get=..`, which opens Compare with the trade filled in.
- The finder reads fixed sources (DDF Value and the four trade charts), so the page has no Customize / Showing row; the league bar stays
  (scoring, teams and roster shape shape the engine rows the search reads). Rosters typed in are kept for the session as before.
- Phone nav: the final nav is 7 tabs (the Writing tab replaces Manifesto, How values work and Research), so no label changes are needed.
- Tests: `test_v2_finder_render` (own tab, not inside Compare, result link opens Compare filled), `test_v2_nav_render` (order),
  `test_v2_hamburger_nav_render` (7 tabs; JEG-953 replaced test_v2_phone_nav_overflow_render), hash sweeps, `live.mjs` `V2_TABS`.
- JEG-854 (same page): Swap teams exchanges the two rosters; each row has a tick box and Move (to the other team); "Move N selected to the
  other team" moves ticked rows; Undo restores the rosters before the last swap or move. Shown results are recomputed after each change.
  Test: `tests/test_v2_finder_arrange_render.py` (3 mutants caught).

## Values auditing shell (JEG-847, 2026-10-22)

- Last tab, `#values-auditing` (view `audit`, page `#v2Audit`, short label "Audit"). Sub-tabs follow the Research precedent: `#values-auditing/health-check` (JEG-1011; was `value-pie`) and `#values-auditing/single-source`; an unknown sub-route shows the Health check. The Showing bar is hidden; the league bar stays.
- Each sub-tab fills its own mount (`#audit-pie-root`, `#audit-source-root`) from its own file (`audit-pie.js`, `audit-source.js`, own CSS) through the `window.DDFAudit` registry in `audit-core.js`: `register(slug, fn)`; v2.js calls `fn(mount, {slug, engine})` on every refresh while that sub-tab shows. Hooks must be idempotent.
- The placeholders are not `.v2-card`, so contract GL-17/GL-18 (chevron and expand control) do not apply until a sub-tab adds cards (then add them to `modules.js` CARDS).
- Phone nav: the stopgap compression for eight tabs (10 px type, 4 px gutter from 360 to 420 px, "Audit" label) was removed by JEG-855, which folds three tabs into Writing (six tabs at the time; Find a trade, JEG-852, made it seven); the original 12 px type and gutter hold at 390 px, with the full "Values auditing" label if it fits. Pinned by `tests/test_v2_nav_render.py`; the shell by `tests/test_v2_audit_render.py`.

## Writing tab (JEG-855, Jeremy, 2026-10-22)

- **What:** Manifesto, How values work and Research are no longer top-level tabs. One tab, "Writing" (`#writing`, short label "Writing", first in the nav where Manifesto was; Jeremy, 2026-10-22; the landing tab stays Trade targets), holds three sections with their own sub-navigation (`.v2-subtabs` / `.v2-subtab`, links with `aria-current="page"`, same shape as Values auditing): `#writing/manifesto` (the default), `#writing/how-values`, `#writing/research` and `#writing/research/<slug>`. An unknown `#writing/...` shows the Manifesto.
- **Old routes:** `#manifesto`, `#how-values`, `#research`, `#research/<slug>` still work. `hashBase()` reads them as their Writing route, and `canonicalizeHash()` rewrites the address with `replaceState` (query kept), so Back skips the old route. Shared links keep working.
- **Pages unchanged:** the three pages keep their containers (`#v2Manifesto`, `#v2How`, `#v2Research`) and their text; only the route, the nav and the in-page links (How popover link, Research index and post links) changed. The sub-nav is `#v2Writing`.
- **Chrome:** the league bar and Showing bar stay hidden on Manifesto and Research and shown on How values work, as before.
- **Contract:** MF-01 (Manifesto is the first section) and RS-01 (sections appear in the order Manifesto, How values work, Research inside Writing) updated. Tests that pinned the old tabs or routes now use the Writing routes; `tests/test_v2_writing_routes_render.py` pins the redirects.

## Nav structure, sub-routes and the audit registry (as merged 2026-10-22, JEG-874)

- **Tabs on `main` 35205b89 (seven, in order; checked 2026-10-23 with `grep -o 'data-view="[a-z-]*"' app/v2/shell.html`):** Writing (`#writing`), Player values (`#values`), Trade targets (`#targets`, the landing tab), Risers & fallers (`#risers`), Compare a trade (`#compare`), Find a trade (`#find-trade`, view `find`, JEG-852, merged #809), Values auditing (`#values-auditing`, view `audit`). Order per Jeremy, 2026-10-22 (JEG-855). `data-view` ids in `app/v2/shell.html`; the list is mirrored in `tests/rendered_gate/live.mjs` `V2_TABS` and pinned by `tests/test_v2_nav_render.py`. JEG-880 proves the nav rules alone with a stand-in eighth tab in `tests/test_v2_phone_fallback_font_render.py`.
- **Sub-route pattern:** a section tab owns `#<tab>/<slug>` routes: `#writing/manifesto` (default), `#writing/how-values`, `#writing/research`, `#writing/research/<slug>`; `#values-auditing/health-check` (default; the old `#values-auditing/value-pie` is a legacy route rewritten by `canonicalizeHash()`, JEG-1011) and `#values-auditing/single-source`. An unknown slug shows the tab's default. Old top-level routes (`#manifesto`, `#how-values`, `#research`, `#research/<slug>`) are rewritten with `replaceState` (query kept) so Back skips them (`tests/test_v2_writing_routes_render.py`). The sub-nav is `.v2-subtabs` / `.v2-subtab` with `aria-current="page"`.
- **`DDFAudit` registry contract (`app/v2/audit-core.js`, #808):** each audit sub-tab is its own file and CSS (`audit-pie.js`, `audit-source.js`) that calls `window.DDFAudit.register(slug, fn)`; `v2.js` calls `fn(mount, {slug, engine})` into that slug's mount (`#audit-pie-root`, `#audit-source-root`) on every refresh while the sub-tab shows, so hooks must be idempotent. The Showing bar is hidden on the tab; the league bar stays. Placeholders are not `.v2-card`, so GL-17/18 do not apply until a sub-tab adds cards.
- **Value pie tab (now the Health check, see "Health check" below; `#values-auditing/value-pie`, #802, JEG-848):** reads `valuePipelineDiagnostics` (`groups[pos|role]` pre-rescale totals, `budgets[pos|role]`, `pie`, `positions[pos].listed/starters/rostered/nEstimated`) and `players[key].adjusted`. Shows per source starter/bench/total Adjusted against the pie (VP-5 holds to rounding), by position, raw vs adjusted, coverage vs rosterable slots, and verdict rows ("Starters: spread X%, within 10%: yes/no"). Flag at more than 10% from the cross-source middle. Copy uses plain source names and "middle value across sources" (#821). JEG-871 (pie total 2352.0 vs the Player values CBS column sum 2430.6) and JEG-872 (source names) are Done (checked in Linear 2026-10-23). Tests: `tests/test_audit_pie.py`.
- **Phone nav rules:** below 768 px the tabs wrap (2026-10-08); below 360 px the seven-tab nav wrapped instead of scrolling sideways (JEG-818, #766); #808's eight-tab compression (10 px type, 4 px gutter, "Audit" label) was reverted by #810 once there were six tabs. JEG-873 (#823, merged 2026-10-22) put the nav on one row at 320 px with an "Audit" label. Since JEG-953 (#864, merged 2026-10-23) phones (under 768 px wide, or a landscape phone up to 932 x 500) show a 44 px menu button that opens the seven tabs as a full-width list with full labels (`app/v2/v2.css`, "JEG-953 hamburger navigation"); the tab row stays from 768 px up. Pinned by `tests/test_v2_hamburger_nav_render.py`. GL-13 (no sideways scroll at 390 px) is the contract line.

## Shared player search (JEG-861 B, #819, 2026-10-22)

One helper, `app/v2/namesearch.js`, serves Player values, Trade targets, Risers (list and disagreements), the Compare add-player boxes, Find a trade rosters and the "Not valued" lists (`curve-widget.js` untouched; `roster-paste.js` keeps its own index). Tokenised; case, accents, punctuation, apostrophes and a trailing Jr./Sr./II/III/IV/V ignored on both sides; every match is a word-start match. Rank: whole name, name start, word start (spaces optional: "amonra"), then every query word starting a different name word in any order ("nacua puka", "j chase"). Fuzzy only when nothing ranks: the spaces-dropped query within 1 edit (4 to 6 letters) or 2 (7 or more) of a whole word or a run cut to the query's length or one longer; no fuzzy under 4 letters, no cut shorter than the query ("nac", "cmc", "arr" match nothing; "kelse" finds only Kelce). Search never invents a player. Tests: `tests/test_v2_name_search.py` (8 mutants caught), `test_v2_name_search_render.py`.

## Customize dialog: two tabs (JEG-850, #811, Jeremy's decisions 2026-10-22)

- Tabs "Chart lines" and "DDF blend" share one draft. The DDF blend tab lists the inputs once (the per-version mirror lists are gone) with "Using N of M sources" on that tab only; a held input is unticked and locked ("Paused this week"); the last usable input is locked ("Last source stays on") and a held input does not count toward it.
- Done is blocked with "Pick at least one source" when the draft has no engine series (no engine change). The VORP group is collapsed unless a VORP series is selected.
- Variants read "DDF Value", "DDF Value: charts only", "DDF Value: projections only". Chips read "Normal range" (green check) and "Under review". A DDF version with no input on says "No sources are turned on for this DDF Value", never "No source prices this player". The strip says "(custom blend)" and counts legend hides; Reset to default clears them. Source links no longer swallow Escape.
- Phone: footer stacks Done, Cancel, Reset (text link); 44 px targets.
- Not changed (recorded on the ticket): rank-by stays DDF Value while its column is hidden (D6); two tab stops per row (D7).
- Tests: `tests/test_v2_customize_cleanup_render.py` (one check per defect, each negative-tested), `test_v2_ddf_versions_render.py`, `test_v2_source_count_render.py`, `test_v2_phone_customize_targets_render.py`. Live re-check on `tv-20261022-2012-1795eb2` passed (JEG-850 comment); JEG-870 (held source still shows the green check) is the one defect found.

## In-range check and source links (JEG-856 A and B, #805 and #806)

- `divergenceChip` (v2.js) is the one helper: in range renders a green SVG check (`.v2-ok-mark`, role img, aria-label and title "Normal range: in line with its usual range ..."); out of range is plain amber text, no box. Feeds Trade targets notes and heads, the strip, Customize and Player values heads. Divergence logic and data untouched. `tests/test_v2_divergence_chip_render.py`.
- Source URLs live in `assets/comparison-sources-data.json` `sources.<id>.url`, else `.source_url`; `v2.js sourceUrl()` reads them; promotion rewrites the weekly articles (usatoday, fantasypros, cbs) from `source_provenance.source_url`. FantasyCalc is `https://fantasycalc.com/trade-value-chart` (a single-page app returns 200 for any path, so the lead checked the page title in a browser). ESPN has no link (Jeremy, 2026-10-22). USA Today answers 402/403 to automation, so its URL is unverified. `tests/test_source_link_urls.py`. Part C (links on the build-up view) was in #803, merged 2026-10-23.

## Trade targets: compare against one source (JEG-851, #807)

`targets.js`: chart keys join `OUR_KEYS`; when Our value is a chart, `effectiveCharts` excludes it; with one compared chart `minCharts` is 1 (else 2) and `buildTargets` returns `singleChart`. `v2.js`: Compare against enables every chart except the current Our value, and the reverse; heading, empty state, footnote and tooltip name the chart instead of "market consensus". Rank-gap, `BUY_RANK_MARGIN` 2, `SELL_FLOOR` 5 and the out/estimated exclusions (JEG-842) are unchanged. Found and fixed on the way: an out-of-scope `TT` reference in `renderTargets()` that errored the page before `window.TradeValueV2.targets()` existed. Follow-ups JEG-868 and JEG-869 are Done (PR #824, merged 2026-10-22).

## Roster paste parser, phase 1 (JEG-853, #804)

`app/v2/roster-paste.js` exposes `window.DDFRosterPaste.parse(text, playerIndex)`: a deterministic parser (no LLM, no network) for a whole-page Ctrl+A copy of an ESPN or Yahoo team or matchup page, matching against the site's own player list and splitting a matchup page into two teams (`benchIncluded` false when the bench is collapsed). Scrubbed fixtures in `tests/fixtures/roster_paste/` parse 15/15, 20/20, 15/15 and 22/22 with zero false positives; nav trap names ("Hodl Beckham Jr") match nothing. Phase 1 wired it to no input; phase 2 (next section) wired it to Find a trade (JEG-852, #809). Assumed, not verified: a bench-expanded Yahoo matchup; ESPN structure across league configurations. Test: `node tests/test_v2_roster_paste.js` (34).

## Roster paste, phase 2: the default input on Find a trade (JEG-853, 2026-10-22)

Jeremy, 2026-10-22: "make dropping in text the default method ... hit control all, copy the whole page, and just drop all the text in ... or look at the matchup page, copy paste all text and it will build both teams."

- Each side of `#v2Find` opens with a paste box (`#v2Find{Mine,Theirs}PastePage`, "Read the pasted page" button, result panel `...PasteResult`), then the name search, then the roster, then the old methods (Sleeper / ESPN league ID / list of names) behind a closed "Other ways to add players" link. The box says the text stays in the browser.
- The paste event or the button calls `DDFRosterPaste.parse(text, engine().getAllRows())`. The engine rows carry `team`, so team and position tie-breaks work. The engine prices QB/RB/WR/TE only, so a K or DEF line is "not in the values" and listed as unmatched: through the UI the four fixtures match 13/15 (Yahoo team), 13/15 (ESPN team), 16/20 (Yahoo matchup), 18/22 (ESPN matchup); the shortfall is K and DEF each time.
- A team page replaces the side's roster with the sure matches (confidence 1: name, team and position agree), each row with the page's own slot (`slot` added to the parser's players: `BN`/`Bench` → Bench, `IR` → IR, ESPN matchup injured and bye lists → Injured / Bye, everything else Starter). A lesser match (nickname 0.9 or "A. Rodgers" 0.8) is shown as "Pasted 'A. Rodgers': is this Aaron Rodgers?" with Yes, add / No, search and is not added until tapped. Unmatched lines carry "Search to add", which fills the side's name search (JEG-861 matcher) and opens it. A player already on the other roster is left there and named.
- Fewer than 3 matched, or under half: nothing is added; "Add these N anyway" is offered. Zero matched (garbage, another site, a league-wide player list, empty): "No players recognised ... Nothing was added."
- A matchup page shows both teams (ESPN team names from the block headers; Yahoo names from the `logo` line before each header, added to the parser) with counts, asks "Which team is yours?", and fills both rosters on one tap; the result says which is which and points to Swap teams (JEG-854); Undo restores what was there. `benchIncluded === false` shows "Bench players are not on this page: expand Show Bench / Show Bench Players ... or paste each team page"; the ESPN result also says what was found ("Found 14 starters, 2 injured, 2 on bye").
- 320 px wide-face +3 px: the Package size select pushed the page 84 px sideways (tap-target agent); `#v2Find .v2-ctoolbar label.v2-field` wraps and the select shrinks.
- Tests: `tests/test_v2_finder_paste_render.py` (four fixtures through the page at 1440 and 375, negatives, lesser match, matchup pick + Swap, 6 finder.js mutants and the 320 CSS mutant caught); `node tests/test_v2_roster_paste.js` (35: slot labels pinned, Yahoo team names asserted). Assumed, not verified: a real phone keyboard paste (the paste event is dispatched synthetically in the test); a bench-expanded matchup page.

## Health check (JEG-1011, Jeremy, 2026-10-24)

The Value pie tab is now **Health check** (`#values-auditing/health-check`, `app/v2/audit-pie.js`, `audit-pie.css`; slug in `audit-core.js`; the old `#values-auditing/value-pie` hash is a `LEGACY_ROUTES` entry in `v2.js`). Spec and iteration log: `fantasy-tools-selfhost-notes/jeg-1011-values-auditing/` (spec.md, changelog.md). Thresholds, how they were derived and validated: `docs/health-check-thresholds.md`.

- **Reading order:** "Is anything wrong?" first (one row per check, one column: Pass / Flag / Info badge, the check's name as a link to its drill-down, a plain reason naming the source and position), then five drill-down sections that each open with a question and a how-to-read line (starters and bench by source, by position, filled-in players, DDF Value reconciliation, and "How do raw and adjusted values compare?", collapsed), then "Terms used on this page".
- **One computation:** `AuditPie.computeChecks()` decides every status; the strip and the amber table cells both read it, so a row can not pass while its table flags. Status never depends on wording.
- **Information, never flags (Jeremy, 2026-10-24):** the QB starter spread and the bench spread. The number is shown with an explanation.
- **Reconciliation (what is checked):** projections' Player values add up to the value pie; a trade chart's Rescaled values for the players it lists add up to their DDF Value (VP-6.4). A chart's whole Player values column does not equal the pie by design, so it is shown, not judged.
- **Single source:** heading "How a source's values are built"; the Published line is drawn as a percentage of the source's own largest value (right-hand axis in %), raw numbers stay in the table.
- **Follow-up, not built:** week-over-week change tracking (new flags since last week) needs stored flag state; ticket-ready note in the notes folder.
- **Tests:** `tests/test_v2_health_check_render.py` (frozen fixtures in `tests/fixtures/audit/`, live page, broken-build guards), `tests/test_audit_pie.py`, `tests/test_v2_audit_render.py`, `tests/test_v2_audit_source_render.py`.

## League workspace: any number of named teams (JEG-1021, 2026-10-24)

Spec: `jeg-1021-league-workspace/spec.md` (decided by Jeremy 2026-10-24: name "Your league", one saved league, K/DEF counted, table on desktop and cards on phone, auto-save with a Saved indicator, up/down reorder; one opportunities table, same for 1 or 20 opponents; team summary; sorting on every numeric column; ranking = fit tier then fundamentals edge; force fits shown with a one-click Hide).

- Files, all with no DOM except `league.js`: `workspace.js` (store, localStorage `ddf.v2.workspaces`, also the shared "my roster" for the Waivers tab: `getMyRoster`, `setMyRoster`, `subscribe`), `table-sort.js`, `team-summary.js`, `opportunities.js`, `league.js` (three cards above the two-team finder on Find a trade). Script order in `build_v2_page.py`: the four pure files, `finder.js`, `league.js`, `modules.js`.
- No value math: starters, bench, depth and fit come from `finder.js` (`lineupValue`, `rosterBalance`, `withChartAverage`, `findTrades`, `tradeFit`), which is unchanged except `api.page` (the page's parser and loaders, shared with `league.js`). The two-team card and all its ids are unchanged (25 test files pin them).
- Constants: market-gap noise floor 2.0 points; median needs 3 teams; at most 20 opponents; 10 trades kept per pairing (the finder's LIMIT); 20 table rows at a time. Listed in `docs/math-review-agenda.md` MR-33.
- Cache: a pairing is keyed by both rosters' values (DDF Value and the four charts) plus the league shape, expected depth and bench weights, so a settings change never reuses an old answer and a rename recomputes nothing.
- a11y: aria-sort is on the th (valid ARIA), one button per header, Market perception is two sub-columns so each sorts from its own header.
- Tests: `tests/test_v2_league_units.py` (Node harness over the frozen fixtures `tests/fixtures/league/`, 22 mutations), `test_v2_league_render.py`, `test_v2_league_tables_render.py`, `test_v2_league_phone_render.py`.
