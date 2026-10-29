# Trade-page parity: shared controls, one data contract, shippable slices (JEG-1220)

Status: Proposal (spec, 2026-10-29). Docs only: no application code, value math, default, ranking, Supabase or deploy
changes. It replaces the 01:24 UTC Codex source audit on JEG-1220 as the code inventory (line numbers there have
moved, and JEG-1219 has shipped since). Copy, labels and empty states stay in the JEG-1221 review
(`docs/product/jeg-1221-trade-page-parity-review.md`, PR #1082); this spec does not repeat its strings.

Jeremy's ask (2026-10-28): "There should be feature parity in filtering and displayed data across the three trade
pages. Right now they all are evaluating trades, but with different controls and data displayed. We should align them."

Pages, and the names the locked plan gives them:

| Today | Locked plan (Jeremy, 2026-10-29 14:24 UTC) | Source |
|---|---|---|
| Find a trade: your team | Find trades, scope "one team" | `app/v2/finder.js` |
| Find a trade: league-wide | Find trades, scope "everyone" (and League for the team cards) | `app/v2/league.js`, `opportunities.js`, `team-summary.js` |
| Compare a trade | Trade | `app/v2/v2.js` (Compare section), `trade.js`, `lineup-comparison.js` |

Evidence base: `main` at `5c07ad6` (2026-10-29), read from source by file and line. No browser QA. Open PR heads read
with `git diff` against their merge base on the same day. Line numbers below are on `5c07ad6`.

## 1. Decisions already in force (not reopened here)

| Decision | Jeremy's words, date | What it settles for parity |
|---|---|---|
| 5A | "5 - A" (2026-10-29, recorded on JEG-1220) | Common preferences are shared across the trade pages through one contract; page-specific controls and state stay separate. |
| Teams | "both teams in find a trade can be picked form the league teams, default the my team to the one starred in league if it has been" (2026-10-29) | Both sides pick saved teams by stable id; Your team starts on the star; no other automatic default. Shipped in JEG-1219. |
| 1a / 2b / 3a | "1a, 2b, 3a" (2026-10-29) | Natural fit = both teams improve starter value (ours on DDF Value, theirs on market), projections do not decline on either side (DDF Value (projections)), both rosters stay healthy. Stretch offers in their own section below. |
| Own-gain ranking | "yes" (2026-10-29 03:13 UTC) to own-gain ranking with modeled opponent-appeal bands | Supersedes 2b's balanced ranking. Bands are labels, not calibrated odds. |
| Natural means both sides | "Natural means both sides, not just 1 side" (2026-10-28) | No one-side check may carry the word Natural (JEG-1221 F1). |
| Three screens | "Yes lock it in and inform codex" (2026-10-29 14:24 UTC) | League, Find trades (one finder with a scope picker), Trade (today's Compare, a deal editor). One carried TradeContext and one both-sides readout everywhere. |
| Tap-to-swap | "make sure when you're evaluating trades when your roster and the trading team roster is loaded, you can easily swap in players between the rosters in that screen" (2026-10-29 14:41 UTC) | Trade screen: tap a player on either roster to move them in or out of the deal; the readout updates in place. |
| Sell gap | "A" (2026-10-29 14:45 UTC) | Per-player market-vs-DDF gap everywhere; league depth (#1105) once every team is loaded, labelled. |
| Chat answers | "A" (2026-10-29 14:47 UTC) | The connector returns the same readout rows and a link that opens the Trade screen with full context. |
| Projections name | D2 = C (2026-10-29 02:03 UTC) | The view stays "DDF Value (projections)". |
| Weekly vs ROS | "do not blend weekly data with ROS data, ever." (2026-10-28) | No readout row mixes the two. |
| Held | JEG-1125 even band | Not lifted. Compare's deal read keeps max(1, 3% of the average side); the finders keep 0.05. Section 4 says where this shows. |

## 2. Parity matrix (main `5c07ad6`)

Class: **Same** = already equivalent. **UI** = a gap that changes no number, default or order. **Contract** = needs the
shared context or readout, still no new number. **Decision** = changes which trades appear, their order or a label
threshold, so it is Jeremy's (section 5).

### 2.1 Context: teams, settings, basis

| Area | Your-team finder | League-wide finder | Compare | Class and target |
|---|---|---|---|---|
| Your team | Saved-team select by stable id (`savedTeamPicker` finder.js:1131); the star pre-fills once (`pullMine` 1142-1153); "Current roster" working copy; paste/search also work | Always the star (`ws.myTeamId`, league.js:1229) | Select by id; defaults to the star (`compareRosterContext` v2.js:5057-5074) | Same rule on all three. TradeContext carries the id with provenance (saved / local / link). |
| Their team | Saved-team select; no default (JEG-1219 decision) | Every other saved team, up to 20 (`MAX_OPPONENTS` opportunities.js:15); opponent is a post-search filter | Defaults to **the first other team with players** (v2.js:5063-5064) | **Contract.** Compare's first-team default predates the teams decision. When a trade arrives with a partner, the partner wins (JEG-1259, #1147). Opened bare, Compare should leave Their team empty like the finder; that is the teams decision applied, not a new default. |
| Writes to saved teams | Never (working copy only, finder.js:1016-1018) | Edits are the saved league (it is the league editor) | Never (v2.js:5035, copy at 5125) | Same intent. Keep: matchup choice is view state. |
| League settings | Engine getters in `run()` (finder.js:1898-1907), `benchWeights` 1584, `depthContext` 1455 | The same getters re-implemented in `mathContext` (league.js:74-92) | Engine read inline; no bench weight in the math (bench is a raw sum in `rosterImpact`) | **Contract.** One `common.league` (TradeContext). The formulas match today; two copies can drift. |
| Value basis label | "DDF Value (basis)" header under a custom basis (finder.js:1499-1501) | No basis label (no `getBasis` in league.js, opportunities.js, team-summary.js) | "Player values shown" picker plus Customize sources; verdict on DDF Value while it is a source | **UI.** Name a custom basis on every page (context line, section 3.2). |
| Bench level | "Modeled" bench (standard) | Standard today; #1105 adds the league-depth market level when every team is loaded | Standard; a trade opened from the league page loses the league level | **Contract.** TradeContext carries the level and the exact rows that priced the trade (`pricing`, #1086); the readout context line names it (decision 14:41 UTC). |

### 2.2 Discovery controls (finders only; Compare gets none)

| Control | Your-team finder | League-wide finder | Class and target |
|---|---|---|---|
| Package size | 1, 2, 3, 4; default 2 (finder.js:24, 976); stored `ui.finderSettings.maxSize` | 2, 3, 4; default 2 (league.js:1048); stored `ui.maxSize` | **UI** to offer 1-for-1 everywhere (default stays 2). **Decision D3** for which stored value wins when the two are merged. |
| Keep my / their starting lineup filled | Two checkboxes, default on (finder.js:2393-2397) | Hard-coded on, no control (league.js:1240) | **UI.** Expose both toggles everywhere; the default stays on, so default results do not move. |
| Protected positions, minimum backups, DDF / lineup minima | Present; stored in `finderSettings` (finder.js:2399-2462; `judgeGuardrails` 91-133) | Not read: `pairingSteps` calls `findTrades` without guardrails (opportunities.js:76) | **Contract.** One shared discovery setting under 5A and the one-finder plan. Defaults are off (workspace.js:28-41), so default results do not move; a reader who set guardrails sees them apply to every scope. The cache key must then include them (2.4). |
| Viable only | Checkbox, default off, not saved (finder.js:979) | None; viability is panel text only | **UI.** Offer on every scope, default off. Uses the existing 0.5 / 1 viability literals (finder.js:283-284) unchanged. |
| Fit, opponent, min capture, min charts fair, hide force | None | Present; defaults all / all / 0 / 0 / off (workspace.js:85) | **UI.** Offer on every scope. Opponent is only shown with more than one opponent. "Min charts fair" values below 3 do nothing (JEG-1221 F4); fix with its copy, not by changing the listing rule. |
| Opponent inclusion | n/a | #1090 / #1092 (JEG-1231): checkboxes for which opponents to search | Becomes the "a few" scope. Already owned. |
| Team-summary column filters, Rank by | n/a | League only (`summaryFilters`, `rankBasis`) | Stay on the League screen. Rank by orders the summary only (JEG-1221 S12). |

### 2.3 Listing, ranking and labels

| Rule | Your-team finder | League-wide finder | Compare | Class and target |
|---|---|---|---|---|
| Listing rule | `judgeSums`: DDF edge above 0.05 and at least `min(3, available)` charts rival-even (finder.js:65-82, `MIN_CHARTS` 23) | Same `findTrades` (opportunities.js:76) | n/a: an explicit deal is never filtered | Same. |
| Order | Groups by received core; best package by size-discounted `scoreOf` (finder.js:139, 26); groups by best edge then score, then re-tiered by fit (`tierGroups` 819-824) | One row per trade: fit tier, edge rounded to 0.1, exact edge, score, size, opponent, id (`compareRows` opportunities.js:136-139) | n/a | **Decision D1.** Same pair of teams can give a different top trade on the two pages. The locked plan ranks by your gain with appeal bands; what "your gain" measures is open. |
| Fit label | `tradeFit` natural / market / force (finder.js:733-763): your DDF total above 0.05 and starters no worse than -0.05; their market net within the noise floor `tau`; construction OK on both | Same `tradeFit`; plus `ourFitOf` "natural / partial / force" sub-label for your side only (opportunities.js:36-41) | No fit label; deal read instead | **Contract** to show the same label on all three through the readout. **Decision D2** for the 1a projection test's tolerance. `ourFitOf`'s one-side "natural" is a defect under "Natural means both sides" (JEG-1221 F1, owned there). |
| Acceptance | "N of M charts winning or even" and viability | Charts fair N/M, viability text | Deal read and split read; `tradeHeadlines` "Will they accept?" exported but never rendered (trade.js:176) | **Contract.** One "Will they accept" row: #1084's appeal band when manager profiles exist, else the chart count. Not new math. |
| Even band | 0.05 (`pointsAsShown`, `NET_FLOOR` finder.js:29, 632) | Same | Deal read `sideOf` max(1, 3% of the average side) (trade.js:315-318); per-source rows 0.05 (`signOf` 92) | **Held (JEG-1125).** Section 4 says how the readout shows both without reconciling them. |

### 2.4 Data shown per trade

| Data | Your-team finder | League-wide finder | Compare | Target readout row (section 3.2) |
|---|---|---|---|---|
| DDF Value net | Card edge | DDF capture pts and % of starters | Verdict, waterfall, per-source table | Value |
| Market net | Chips, delta line | Market edge column | Deal read net (chart mean) | Value (their side) |
| DDF Value (projections) net | Chips, delta line | Projections agree / disagree | Deal read third net | Projections, per side |
| Starters before and after | Both sides, DDF and market (finder.js:2045-2091), own `lineupTable` (2030) | Both sides, DDF and market, `renderTable` (league.js:938) | **DDF Value only, both sides** (v2.js:5233-5236) | Starters: ours on DDF Value, theirs on market (1a), both shown in both views on request |
| Bench and roster after | Bench delta per view | Their fit: construction | Empty starting slots, roster spots opened or used (v2.js:5274-5279) | Roster health (JEG-1230) |
| Fit label, viability | Yes | Yes | No | Verdict row |
| Single-source and estimated tags | No | No | Yes (`appendLowConfidence`, v2.js:5411, 5700) | Data labels (JEG-1221 F2) |
| K/DEF and unpriced players | Not evaluated; left out of sums | Chips; left out | "not in values" for both | Data labels, three states (JEG-1221 S8-S10) |
| Context (scoring, teams, superflex, basis, bench level) | Not shown on the card | Not shown | League bar only | Context line |

### 2.5 Persistence, links and hand-offs

| Area | Your-team finder | League-wide finder | Compare | Class and target |
|---|---|---|---|---|
| Stored | `ddf.v2.workspaces` `ui.finderSettings`; sessionStorage working copy with saved-team ids (finder.js:1026-1059) | Workspace `ui` (size, filters, sort, rank basis, summary columns) | Only the Customize list (`ddf.v2.pages`) | Common preferences once (TradeContext `common`); discovery controls once (slice 1); route view state separate. |
| Share link | `#find-trade` with both rosters, package, keep flags, guardrails, league query, basis and overrides (`encodeFinderHash` finder.js:887-910). No saved-team ids, viable-only or selected group | `#find-league` with team names and keys, my-team index, league query, basis and overrides (workspace.js:215-219). **No discovery controls**; the selected trade lives only in the address bar, keyed by **opponent name** (league.js:900-929) | `#compare-trade` give/get plus league query, basis and overrides (v2.js:6195-6213). **No teams**: `readTradeHash` hands mine/theirs to the finder's sides, not Compare's (ddf-assist.js:139-146) | **Contract.** Each route's link carries the same `common` block, its own controls, and team identity by stable id; a carried trade carries its partner. Selected trade by opponent id, not name (teams decision). |
| Open in Compare | `v2/#compare-trade?give&get`, ids only (finder.js:2221) | `#compare-trade?give&get`, ids only (league.js:895, 1190) | n/a | **Contract.** Send a TradeContext transfer: rosters, partner, settings, basis, bench level (JEG-1259). |
| Back to results | n/a | n/a | Tab bar only | **UI.** A "Back to results" link when the trade came from a finder. |
| Result cache | None (re-runs on Find) | `contextSig` covers shape, charts, market, size, keep flags, expected depth, weights (opportunities.js:91-94); not guardrails (not applied today) | n/a | Use TradeContext `cacheKey(context, "discovery")`, which includes every applied control. |

## 3. Shared contract

### 3.1 TradeContext (JEG-1229, PR #1086; carry-over JEG-1259, PR #1147)

`app/v2/trade-context.js` already implements the shape this spec needs. The parts and what each route may change:

| Part | Shared across routes (5A) | Route-specific |
|---|---|---|
| `common.league` | Scoring, team count, roster shape, shares, weeks, advanced; via the DDFState codec, all or nothing | - |
| `common.valuation` | Basis and overrides, with link > local > saved precedence (`resolveCommon`) | - |
| `common.sources` | Availability and held / paused reasons | - |
| `teams` | Saved-team ids and frozen roster snapshots with provenance | Which teams are in play: pair = one partner, league = opponents, Compare = one partner |
| `deal` | - | Explicit give/get keys (Compare, and a found trade opened anywhere) |
| `controls` | - | Discovery controls for the finder (slice 1); Compare has none and warns if any are passed (`createContext`) |
| `pricing` | Bench level and the identity of the rows that priced the trade | - |

Rules the slices keep:

- A route reads `common` through the context, never its own copy of the engine getters (closes the `mathContext` duplicate).
- Matchup selection is view state: no route writes the star or a saved roster while choosing teams.
- A visit from a link starts with `beginVisit`; Cancel or Undo restores the earlier visit context; nothing from a link is saved without `maySave` (JEG-1114, PR #1123, owns the cross-tab part).
- A deleted or missing team id stays an explicit missing selection; a rename keeps the same id.
- `ROUTE_DISCREPANCIES` in `trade-context.js` lists today's route differences. Each slice below that closes one removes its entry in the same PR, so the list is the running parity backlog.

### 3.2 The both-sides readout (JEG-1230, PR #1088; second half is slice 4)

One pure adapter (`app/v2/trade-readout.js`) builds the rows from what `finder.js` already computes; `lineup-comparison.js`
draws them. Every page renders the same rows in this order (Value first, #1093):

| Row | Mine | Theirs | Source today | Owner |
|---|---|---|---|---|
| Value | DDF Value net; DDF Value (projections) net | Market net; charts even-or-winning N of M | `rosterImpact`, `withChartAverage` | JEG-1230 (#1088) |
| Starters | Before → after on DDF Value | Before → after on market (1a) | `pickStarters` via `rosterImpact` | JEG-1230 (#1088) |
| Projections | Change on DDF Value (projections) | Change on DDF Value (projections) | same | JEG-1230 (#1088) |
| Roster health | Open starting slots, bench count, reserve slots known or not | same | `rosterCount`, `needLine` | JEG-1230 (#1088), JEG-1260 |
| Verdict | Natural fit / Market supported / Force fit, with which test failed | | `tradeFit`, then the 1a predicate (slice 5) | slice 4 |
| Will they accept | | #1084 appeal band when profiles exist, else viability and chart count | `manager-recs.js`, `viabilityLabel` | slice 4 |
| Sell gap | Per-player market-vs-DDF gap; league depth when every team passes #1105's completeness check, labelled | | `team-summary.js`, #1105 | slice 4 |
| Data labels | Single-source, estimated, K/DEF not evaluated, no value this week, override | same | `appendLowConfidence`, `isNotEvaluated` | slice 4 (strings from JEG-1221) |
| Context line | Scoring, teams, superflex, basis, bench level, week | | TradeContext `common` and `pricing` | slice 4 |

A missing roster renders the Value rows and an inline paste prompt in place of the other rows; it never blocks the
section or shows 0. A held or unavailable view shows its reason (`sourceStatus`), never 0.

### 3.3 The parity test every slice extends

`tests/test_trade_page_parity.py` (new, slice 7): one explicit trade on the USO fixture (`tests/fixtures/uso_site_journey/`,
PR #1110) opened (a) on the pair finder, (b) on the league finder with that opponent, (c) in Compare from "Open in
Compare", and (d) in Compare entered by hand. Pass when every readout row is identical to 0.1 point as rendered on all
four, in Standard, Half PPR and PPR at 12 teams, and when it fails on a copy of the pages with one route reading its
own engine getters. It extends JEG-1221 AC1 and the readout's own parity test in #1088.

## 4. Where the held even band shows (no decision asked)

With the readout on Compare, a trade can read "Natural fit" (finder band 0.05 and `tau`) beside a deal read of "even"
(Compare's max(1, 3%)). Until JEG-1125 is decided the readout shows the verdict row from the fit rule and keeps
the deal read in its own card, labelled as Compare's read, with no sentence claiming they agree. This is presentation
only and does not change either band.

## 5. Decisions for Jeremy

These are the only open choices this spec found. Everything else in section 2 is UI or contract work under decisions
already made.

Status 2026-10-29 (14:58 CT): **A on D1, D2 and D3 are Claude picks**, made under Jeremy's standing "Yes, use your
picks, and make a note of what was picked" (2026-10-28) and logged in the coordinator's picks log. Jeremy can reverse
any of them. They are not his decisions. The slices build on them, and each slice's merge still waits on his OK by PR
number. The ticket also requires numerical tolerances to go back to Jeremy for review, so slice 5 (D2) shows him the
before/after label counts and the near-zero boundary examples before it merges.

**D1. When the finders become one finder, what does "your gain" rank by?** Today the your-team finder discounts
bigger packages (each player past a 1-for-1 takes 10% off, `EXTRA_PLAYER_WEIGHT` finder.js:26) and folds trades by the
player you receive; the league finder ranks by raw DDF edge (rounded to 0.1) and only uses the discount to break ties.
So the same two teams can top-list different trades.

- A. Rank by DDF Value edge, then the size discount as a tie-break, then fold by received player on the first page
  (the league finder's order, applied to every scope).
- B. Rank by the size-discounted score, folding by received player (the your-team finder's order, applied to every scope).
- C. Keep each scope's order as it is today.

Pick (Claude, reversible): **A**. The own-gain decision reads most directly as the DDF edge, and A changes the order on one page
only. B favours small packages in a way the page never explains; C leaves the parity gap Jeremy asked to close.

**D2. How much may projections fall before a trade stops being Natural (1a)?** 1a says "projections do not decline"
on both sides, without a tolerance. The finder's other Natural tests use the 0.05 display floor for your side and a
noise floor (`tau`) for theirs.

- A. 0.05, the display floor: a fall that shows as 0.0 still counts as not declining, on both sides.
- B. The noise floor `tau` per side, the same tolerance their market test uses.
- C. Exactly zero: any fall fails.

Pick (Claude, reversible): **A**. It matches what the reader sees on the card, so a "Natural" trade never shows a negative
projections change. The 14:24 UTC check found several current Natural trades that fail 1a on projections (for
example their projections falling 2.2); those fail under A and C, and under B only if 2.2 is past that side's noise
floor, which this spec did not measure. The slice must ship near-zero boundary examples either way.

**D3. Package size is stored twice (pair `finderSettings.maxSize`, league `ui.maxSize`). Which one survives the merge?**

- A. The your-team finder's setting, with the league value dropped on first load.
- B. The league finder's setting.
- C. Whichever is larger.

Pick (Claude, reversible): **A**. It is the setting that also stores the guardrails, so one record holds every discovery control.
Pre-launch there are no readers' saved values to lose. The default stays 2 under every option.

## 6. Slices

One slice = one PR. "In flight" rows are owned elsewhere and listed only for ordering. Hot files (AGENTS.md):
`app/v2/v2.js` is one; `finder.js`, `league.js` and `trade.js` are not hot but are crowded, so the order below
serialises them.

### 6.1 In flight (do not duplicate)

| PR | Ticket | Files this spec cares about | What it gives parity |
|---|---|---|---|
| #1086 | JEG-1229 | `trade-context.js` (new) | TradeContext module |
| #1147 | JEG-1259 | `trade-context.js`, `v2.js` | Compare receives a carried trade's rosters and values, or holds and says why |
| #1088 | JEG-1230 | `trade-readout.js` (new), `lineup-comparison.js` | Readout rows: value, starters, projections, roster |
| #1123 | JEG-1114 | `finder.js` | Opened links keep their settings across tabs |
| #1124 | JEG-1225 | `overrides.js`, `ddf-value-link.js`, `mcp/tools.ts`, get-values | Chat prices under a link's basis and overrides |
| #1084 | JEG-1217 | `manager-recs*.js`, `manager-profiles*.js` (new) | Appeal bands and Stretch section |
| #1090, #1092 | JEG-1231 | `opponent-inclusion.js` (new), `league.js` | "A few" scope |
| #1093 | JEG-1232 | `league.js` | Fixed column order, Value first |
| #1100 | JEG-1237 | `finder.js`, `v2.css` | Finder results on the first screen |
| #1105, #1145 | JEG-1188, JEG-1273 | `league.js`, `workspace.js`, engine files | Two bench levels; league problems list |
| #1091 | JEG-1233 | `league-status.js` (new) | Loaded-league status |
| #1082, #1138, #1037 | JEG-1221, JEG-1130 | copy in `finder.js`, `league.js`, `team-summary.js` | Labels and empty states |
| #1033 | JEG-1125 (held) | `finder.js`, `trade.js` | One even constant; held, don't merge around it |
| #1057, #1119, #1032 | JEG-1115, JEG-1179, JEG-1123/1124 | `mcp/tools.ts` | Connector fit and size fixes |

### 6.2 New slices

| # | Slice | Files | Depends on | Collides with (merge after) | Done when |
|---|---|---|---|---|---|
| 1 | Shared discovery controls: one normalized record (size 1-4, keep flags, guardrails, viable only, fit, opponents, min capture, min charts, hide force), with the D3 migration | `app/v2/discovery-controls.js` (new), `tests/node/discovery_controls_check.cjs` | #1086 API; D3 | none (new file) | Normalizing today's two stored shapes gives today's values; a test fails when either route's default would change |
| 2 | League finder reads slice 1: 1-for-1 offered, keep toggles shown, guardrails applied, cache keyed by TradeContext | `league.js`, `opportunities.js` | slice 1 | #1092, #1093, #1105, #1145, #1138 (league.js) | On the USO fixture with default controls the rows are identical before and after; with one guardrail set, a test that fails without the change |
| 3 | Pair finder reads slice 1 and gains fit, opponent-free filters and hide force | `finder.js` | slice 1 | #1123, #1100, #1138, #1033 (finder.js) | Default results identical; a fit filter test that fails without the change |
| 4 | Readout rows second half: verdict, will they accept, sell gap, data labels, context line | `trade-readout.js` | #1088 merged; slice 5 for the 1a verdict (until then the verdict row reads `tradeFit`); #1084 for bands | #1088 (same file) | Golden fixture rows for one trade with a held source, a K, an unpriced player and a single-source player |
| 5 | Natural fit 1a predicate in shared code; the finder label and `ourFitOf` move onto it (T1) | `finder.js` (`tradeFit`), `opportunities.js` | D2 | slices 2 and 3 (same files); #1033 held | Before/after label counts on the fit diagnostic (`tests/node/fit_diagnostic.cjs`), the 14:24 UTC examples flip as expected, near-zero boundary tests |
| 6 | Trade screen mounts the readout and replaces the DDF-only construction section; Their team no longer auto-fills when opened bare | `v2.js` (hot) | #1147 merged; slice 4 | #1147, #1035, #1012 (v2.js) | Compare renders their starters on market; Their team empty on a bare visit; contract render test |
| 7 | Both finders mount the readout in their detail panels; the parity test (3.3) lands here | `finder.js`, `league.js`, `tests/test_trade_page_parity.py` | slices 2, 3, 4 | slices 2, 3 | Parity test green on all four entry paths and failing on a broken copy |
| 8 | "Open in Compare" sends a TradeContext transfer from both finders; Compare links back to results | `finder.js`, `league.js` | #1147 merged | slice 7 (same files) | A found trade opens with both rosters, partner, basis and bench level; JEG-1240's journey test (#1110) extended |
| 9 | Share links carry `common`, the route's controls and team ids; the league's selected trade by opponent id | `workspace.js` (`shareHash`), `league.js`, `finder.js` (`encodeFinderHash`) | slice 1 | #1105 (workspace.js), #1123 | Round trip of every field; an old link still opens |
| 10 | Connector returns the readout rows for both sides; finder links carry full context to the Trade screen | `supabase/functions/mcp/tools.ts`, `state.ts` | slice 4; #1124 | #1124, #1119, #1057, #1032 (tools.ts) | `slimOffer` has their market net, their starters change and both fits; the league link keeps every team, not only `mine` (tools.ts:1054-1058). Deploy needs Jeremy's fresh yes per function |
| 11 | One finder with a scope picker (one team / a few / everyone) | `finder.js`, `league.js`, `shell.html`, `v2.js` routes | slices 2, 3, 7, 8 | everything above | Parent ticket with sub-tasks; both old routes redirect |
| 12 | Trade screen tap-to-swap on both loaded rosters with a sticky summary | `v2.js` (hot) | slice 6 | slice 6 | Tap moves a player in or out, the readout updates without resetting scroll or context |

Out of this spec, tracked by the locked plan: the League screen's per-team strengths and weaknesses with "Find
trades with them" (builds on JEG-890 / #964), and the Fieldnotes design (JEG-1209, JEG-1138). Parity is not design
approval.

### 6.3 Order

1. Merge the in-flight foundations: #1086, then #1147, then #1088 (the readout's first half).
2. Slices 1, 5 (after D2) and 4 can be built in parallel: new file, `tradeFit`, and `trade-readout.js` don't share hunks.
3. Slice 2 after the league.js queue (#1093, #1092, #1105/#1145); slice 3 after #1123 and #1100.
4. Slice 6 (v2.js) after #1147; then slice 12.
5. Slices 7 and 8 (both finders' files) after 2 and 3.
6. Slice 9, then slice 10 (connector, with deploy approval), then slice 11.

Each value or label change (slice 5) pairs with the Python reference where one exists and runs `make validate`, the
rank guard and `value_check compare` as AGENTS.md requires. The other slices change no number; their Done-when is the
"default results identical" check plus a test that fails without the change.

## 7. What this spec could not check

- No browser QA here: cloud sessions can't run Playwright Chromium. Rendering claims are from source.
- Line numbers for `finder.js`, `league.js`, `v2.js` will move as the in-flight PRs land.
- JEG-1214 (interactive Compare) is Done and has no live owner, so slices 6 and 12 need an owner assigned.
