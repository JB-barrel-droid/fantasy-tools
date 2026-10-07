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

Not yet mapped: 03/04 Market disagreement, 05/06 Risers & fallers, 07/08 Compare a trade,
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
