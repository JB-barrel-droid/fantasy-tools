# Current trade-page controls and data parity (JEG-1220)

This supplements [the merged parity proposal](trade-page-parity.md), rather than replacing its decisions or its twelve owned slices. It inventories source on main `992c8525` for Jeremy's requested Mac refresh. No runtime or numerical change is proposed for immediate release.

Status: Proposal; source verified 2026-11-01 CT. No browser or live-number verification.

## Controls inventory

The three surfaces are the pair finder (`finder.js`), league finder (`league.js` and `opportunities.js`), and Compare (`v2.js` Compare section and `trade.js`). Paths below are under `app/v2/`. Global shell controls appear on all three; duplicating their widgets is unnecessary.

| Control family | Pair finder | League finder | Compare |
|---|---|---|---|
| Scoring and league size | Shared Your league panel: Standard, Half PPR, Full PPR; 8/10/12/14 teams | Same; also offers matching league size to loaded team count when supported | Same |
| Starting roster and superflex | Shared slot steppers: QB/RB/WR/TE/FLEX/SUPERFLEX, K/DEF and bench; superflex is a slot count | Same | Same |
| Horizon and advanced league settings | Shared season-weeks/optimization controls, content week, injury history, projection confidence, bench-share override | Same | Same |
| Source/basis customization | Shared DDF basis, source selection, position weights, player overrides | Same engine inputs; custom basis is less visible in local labels | Player values shown series picker and Customize sources additionally select displayed series; verdict basis can differ from displayed series |
| Team selection | Both saved-team selectors; Your team initially starred; Their team unselected; local working copies | Star marks Your team; other saved teams searched; stable-ID opponent inclusion checkboxes, Select all/Clear; manager won't-trade exclusions | Saved roster selectors or carried trade context; explicit give/receive sides; bare-route opponent fallback still recorded in trade-context.js |
| Roster entry/edit | Search/add, paste names or matchup, ambiguity confirmation/search, clear each/both, Undo, swap teams, select/move/remove players, edit/collapse rosters | League name/workspace selection and save/load; add/name/remove/star teams; roster paste/search/add/remove, ambiguity resolution, league import/paste confirmation, clear league/Undo; edits persist saved teams | Add/remove explicit Give/Get players, search, clear deal, swap sides, sample trade; loaded-roster player toggles and roster selectors; edits evaluate a deal, not a search |
| Package size | 1-for-1 only, up to 2/3/4 per side; default 2 | Up to 2/3/4; default 2 | Explicit deal size, no search cap |
| Starting lineup protection | Keep my starters / keep theirs checkboxes, both initially on | Both hard-coded on at search call; no toggles | Reports health; does not hide an explicit deal |
| Position protection | QB/RB/WR/TE protected starters checkboxes | Absent from pairing call | No discovery filter |
| Backups | QB/RB/WR/TE minimum backup +/- steppers, 0–20, default 0 | Absent | No discovery filter |
| Advanced trade minima | Minimum DDF gain; own lineup gain; opponent market lineup gain (0–100, step 0.1; blank lineup minima off); reset settings | Not forwarded | No discovery filter |
| Result filters | Show viable offers only; received-core player selection/package editing; expand alternatives and more groups | Overall fit all/natural/natural+market; opponent; min capture 0/1/3/5/10; min charts fair 0–4; hide/show force; team-summary rule filters (side/field/operator/value, add/remove) | No discovery filter; source customization controls which comparison rows appear |
| Sorting and presentation | Groups by received core, fit tiers, package alternatives | Sortable opportunity columns; more results; summary Rank by DDF/market, column visibility and summary sorting, team/opportunity details | Per-source comparison, waterfall and roster/lineup detail; choice of displayed series |
| Sharing/navigation | Find trades, copy search link, open package in Compare | Find opportunities, copy league/search or selected-trade link, details, open in Compare | Copy trade link; navigation among site tabs |

Source anchors: `v2.js:3115–3405` (global league editor), `finder.js:1980–2115` (roster editor), `finder.js:2649–2765` (discovery widgets), `league.js:1342–1362` (filters), `league.js:1540–1556` (search arguments), `v2.js:5153` onward (Compare context and editor). See the individual modules for generated controls, not just HTML templates. This inventory groups repeated player-row buttons and common panel open/close actions by function.

## Reads and numerical disagreement paths

| Layer | Pair | League | Compare | Parity risk |
|---|---|---|---|---|
| Values and identity | `TradeValueCurveControls.getAllRows()`, source availability and roster shape; stable player keys | `mathContext()` builds rows/maps from the same engine plus league-level pricing | `C.getAllRows()`, selected series, carried `TradeValueTradeContext` | Same player name is insufficient: compare stable key, scoring, week, basis, overrides, source availability and pricing fingerprint |
| Saved/local state | Workspace `ui.finderSettings`; session working rosters | Workspace teams/provenance, `ui.maxSize`, filters, inclusion IDs, summary preferences | Explicit deal, page source preferences and optional transferred rosters/pricing | Separate size records and route-local edits produce different searches; selection must not mutate saved rosters or star |
| Search | `findTrades` with guardrails and chosen keep flags | Same function via `pairingSteps`, without guardrails and with keep flags true | No enumeration | Candidate sets legitimately differ today even for the same teams; test enumeration separately from readout |
| Replacement/bench | Modeled bench and engine bench-share weights | With complete, fresh, matched league: DDF replacement/weights from available league players, market depth from active rostered players; otherwise modeled with reasons | Modeled when bare; transferred pricing/context when carried | Complete league can change values, starters, bench-weighted gains and Natural fit. Never silently recompute a carried league trade on modeled rows |
| Market and projections | Available chart keys, chart average and DDF Value (projections) | Same source families, league pricing may change values | Per-source rows, chart mean, projection read and verdict | Held or missing sources alter denominators. Missing values stay null; K/DEF remain excluded, not zero. Weekly and ROS must remain separate |
| Fit/readout | Finder fit/lineup helpers; shared readout available | Same helpers plus opportunity flattening/ranking | `trade.js` verdict/story; shared `trade-readout.js` adapter exists separately | The shared adapter is not yet invoked by these three route files; module parity does not prove visible route parity |
| Ordering | Received-core grouping and size-discounted best package | Flat rows, fit then rounded/raw edge and tie-breaks | No recommendation ordering | Different top results do not prove different explicit-deal arithmetic |

Underlying engine inputs include baked player rows and comparison source artifacts, selected week/history and source freshness/availability, roster/lineup settings, basis, position weights and overrides. Pages consume engine output rather than independently fetching a new projection feed. League workspace provenance determines whether league-derived levels are usable (`league.js:77–105`). Missing/held projection inputs must prevent a false Natural conclusion. Raw roster totals, starter values and bench-weighted gains are distinct measures and must be named.

Resolved since the older spec: `trade.js:85–104` now defines the shared `evenBand = max(1, 3% of average side)` (JEG-1125 option A); 0.05 is a display/fit floor, not an alternative win/even/lose rule. `tests/test_trade_bands.py` checks the actual band behavior. Stable-ID inclusion and selected-trade links now exist (JEG-1231/JEG-1328). `trade-context.js` and `trade-readout.js` exist with focused tests. The October proposal's held-band section and statements that these modules are future work are historical, not current requirements. This refresh grants no new numerical authority.

## Proposed shared set and implementation boundary

Retain the approved three-screen plan and 5A: one normalized common context (league/scoring/slots/week/horizon, basis/sources/weights/overrides, availability and pricing provenance); one both-sides explicit-trade readout; stable team IDs with roster snapshots. Reuse `trade-context.js` and `trade-readout.js`, not a fourth implementation.

Both discovery scopes should read one stored discovery record: package 1–4, both keep flags, protected positions, backup minima, trade/lineup minima, viable-only, fit/capture/chart filters and hide-force. Opponent inclusion is meaningful only for multiple opponents. Preserve approved defaults until migration and ranking choices are confirmed. Include every result-affecting field in cache identity; `opportunities.js:contextSig` currently omits guardrails because pairing does not use them. Do not add a control without forwarding it through search and cache keys.

Compare shares evaluation context and readout, while keeping its explicit-deal editor and series picker. It must show an unfavorable deal rather than filtering it out. League editing, summary columns/ranking, manager profiles, selected result, expansions, sorting and working roster edits remain route state. Opening Compare carries exact rosters, opponent identity, pricing rows/fingerprint and settings; it never changes the saved league star. A bare editor cannot claim full roster effects without full rosters.

Implement through the existing twelve slices in the merged proposal, keeping their child ownership and merge order. This audit does not revive deferred screen work or duplicate child PRs; the ticket's Nov 1 direction puts new screen work into the redesign.

## Parity test plan

1. Cheap inventory check: `tests/test_trade_control_parity_inventory.py` records three observed UI gaps as individual expected failures: package choices, lineup toggles, guardrail forwarding. It reads current source and asserts the desired contract; missing anchors fail normally. An unexpected success fails so the obsolete exception must be removed. This is a source inventory alarm, not browser or numerical parity proof.
2. Keep existing numerical checks: `tests.test_trade_bands`, `tests.test_jeg1230_trade_readout`, `tests.test_jeg1229_trade_context`. They exercise shared arithmetic, explicit-deal edge cases, codecs and context. No new baseline that simply blesses numerical drift. The Mac focused run found the existing context wrapper failing in its JEG-1240 journey case (`envelope`: undefined `settings`); the other 29 Node context checks passed. Readout and band wrappers passed. This is not a green context-suite claim.
3. Route acceptance: open the same stable-key explicit trade in pair results, one-opponent league results, carried Compare and manually entered Compare. Compare raw totals/net, per-source completeness, starters before/after, bench/health, both projection deltas, fit, chart acceptance count and context label. Rendered values equal at 0.1 point; raw values should match before formatting when pricing context matches.
4. Cover 3 scorings × 4 sizes, superflex on/off, different roster shapes, default/custom basis and overrides; modeled versus complete-league pricing are separate labeled cases. A carried league trade must retain its pricing. Do not demand equal numbers across intentionally different contexts.
5. Exercise held/missing/single-source inputs, K/DEF, unmatched/duplicate keys, zero versus null, weekly/ROS separation, incomplete/stale/bench-omitted league, near-zero projection declines and even-band boundaries. Cover rename/delete/star changes, same-name opponents, old/new links, reload and conflicting stored discovery sizes.
6. Assert shared preferences survive navigation, route-only state does not leak, toggles affect candidate enumeration, changing any guardrail invalidates the league cache, and selected result transfers preserve identity. Deliberately mutate one route's settings/rows and require a parity failure. Before runtime publication, run the required render and validate gates sequentially through the owning lane.

## Questions for Jeremy (recommendation first)

Settled 5A, Natural semantics, three screens, own-gain direction, team selection and shared trade band are not reopened. Earlier D1–D3 were reversible Claude picks, not new Jeremy approvals.

1. **Migration when package sizes conflict:** A (recommend) retain the earlier D3 pick: pair `finderSettings.maxSize` wins once; B retain league size; C ask on first conflict. Both defaults remain 2. This needs confirmation at migration, not to merge this inventory.
2. **Redesign sequencing:** A (recommend) use this inventory as acceptance criteria for the redesign and keep numerical plumbing in existing children, following your Oct 30 option A; B schedule a separate controls-only patch on today's screens. No parallel screen implementation is started here.
3. **Numerical boundary sign-off:** A (recommend) keep existing semantics while the owning slices present D1 ranking and D2 tolerance impact examples for review; B request a new numerical proposal before any remaining parity slice. No tolerance or ranking formula is approved by this document.
