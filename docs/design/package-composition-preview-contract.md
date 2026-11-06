# Selected-package composition preview: contract (JEG-1275)

Part of JEG-1183. An isolated component that shows a package of trades someone else has already chosen. It is not the
optimizer, and it does not finish JEG-1183.

Files: `app/v2/package-composition-preview.js` and `.css` (global `TradeValuePackagePreview`). Tests:
`tests/test_package_composition_preview_contract.py` (node, no browser) and
`tests/test_package_composition_preview_render.py` (Playwright). Fixtures: `tests/fixtures/package_composition_preview/`
(`cases.json`, `preview.html`), all synthetic and labelled so on screen.

## What it shows

- The trades in the order given, each with its counterparty and the players listed on each side, behind a keyboard
  disclosure (a button with `aria-expanded` and `aria-controls`).
- Counts of the shown composition only: trades shown, distinct counterparties named, players listed to give and to get.
  A player listed twice counts twice; whether that is allowed is the roster check's answer, not the count's.
- The roster check: passed, failed (every supplied error, in the supplied order, with the supplied text), unavailable, or
  not checked (empty selection). Every trade stays on screen; a trade is flagged when a supplied error names its
  `tradeIndex`.
- The final lineup, only from a separately supplied lineup adapter, before and after, row for row as supplied.

## What it never does

- Select, rank, search, sort, price or re-order trades or packages. A reversed package renders reversed.
- Re-implement the JEG-1262 rules. The roster check is injected; the preview only reads its answer.
- Show `applyPackage`'s rosters as a lineup. They keep each player's recorded slot (the synthetic fixture ends with three
  "RB" slots), so without a lineup adapter the section says "Final lineup unavailable" and `applyPackage` is not called.
- Recalculate, fill or re-slot a lineup. An empty starting slot is shown as "Empty" and the lineup is marked incomplete.
- Write storage, fetch, or mutate its inputs (tests run on deep-frozen inputs under strict mode).

## Context

```
{fixture?: {kind: "synthetic" | "historical", label},
 league:  {myTeamId, teams: [{id, name?, entries: [{key, name, pos, slot?}]}]},     // as JEG-1262 reads it
 trades:  [{opponentId, give: [ref], receive: [ref]}] | null,                       // preselected, in order
 package: {validatePackage(league, trades), applyPackage(league, trades)} | null,   // the JEG-1262 adapter
 lineup:  {lineups(league, appliedLeague) -> {before, after, complete?, missing?: [text]}} | null}
ref  = key string | {key} | {player_key}, optionally with name
side = {starters: [row], bench: [row]};  row = {slot, key, name}
```

The roster-check answer must be `{ok: true, errors: []}` or `{ok: false, errors: [non-empty]}`. Anything else (missing
adapter, a throw, an unreadable or self-contradicting answer) is "Roster check unavailable", never "passed". The lineup
is asked for only when the check passed, a lineup adapter is supplied and `applyPackage` returns `{ok: true, league}`.

## Runtime hook (not in this ticket)

Waits on the reviewed JEG-1262 helper (PR 1116) and a real lineup adapter owned by JEG-1249 / JEG-1230. Tokens and the
shell stay with JEG-1137. `finder.js`, `opportunities.js`, `league.js` and shared UI are not touched.

## Known limits

- The JEG-1262 error text counts trades from 0 ("trade 0 names z") while the preview numbers trades from 1. The text is
  shown as supplied; a wording change belongs to the helper's owner.
- A duplicate-counterparty error carries one `tradeIndex` (the later trade), so only that row is flagged.
- The render test needs Chromium. It skips locally without one and errors under `RENDER_TESTS_REQUIRED=1`. It is not
  yet in a Makefile run list or workflow (the CI coordinator owns that wiring).

## Greedy selector companion (JEG-1183, 2026-11-03)

`app/v2/trade-package-search.js` exports `TradeValuePackageSearch.selectPackage(league, candidates, ctx)` in the
browser and `selectPackage` under Node. This separate pure module selects trades; the preview above still only
displays the selection. It follows the settled Oct 29 decision: greedy, re-checked after every trade.

Pass the complete completed opportunities result, before pagination or `capPerCore`, and its exact pricing snapshot:
`ctx = {rowsByKey: Map, shape, expected, weights?, charts, market, keepMine?, keepTheirs?, minCharts?, guardrails?}`.
`charts` names available search charts; `market` names the available charts used for the market mean and must include
at least the finder's minimum three. Missing context or an unresolved valued roster entry produces
`{ok: false, status: "unavailable", errors, trades: [], league: null, edge: null}`. K/DEF entries without pricing
rows remain in the final rosters and stay outside valued lineup calculations.

For every remaining candidate, every round:

1. Validate the entire selected prefix plus the candidate against the original league with `TradePackageConstraints`.
   This enforces original ownership, each counterparty once and each player once, including incoming players.
2. Resolve players from `rowsByKey`, ignoring cached candidate prices, fits, ranks and gains. Rebuild the current
   rosters' market means and call `evaluateCombo`, including current-roster sanity and any supplied guardrails.
   Moving players need finite DDF Value and market values; missing values never become zero.
3. Call the existing `tradeFit` and live `viabilityLabel` on those current rosters. Keep candidates that pass all
   search gates and have a live viability label. Rank with `opportunities.rankRows`: fit tier, DDF gain, finder
   score, size, opponent name, stable trade identity. Viability confidence is a gate, not a new ranking rule.
4. Apply the best candidate with `applyTrade`, then repeat until none remain. Previously rejected candidates are
   reconsidered because another trade can change their fit or viability.

Success returns `{ok: true, status: "ready" | "empty", method: "greedy_rechecked", errors: [], trades, league, edge}`.
`trades` contains refreshed fit, viability, edge, score and selection-order rank. `league` is the final sequential
roster state, not a lineup. `edge` sums selected trades' DDF gains; it is not a lineup-value delta. The existing
preview accepts the selected trades unchanged, with a separate lineup adapter using the live `pickStarters` helper.

The search does not regenerate offers excluded from the completed opportunities result and does not claim an
exhaustive global optimum. Route registration, refreshing on context changes, and the production panel remain
with JEG-1183's shared-route integration owner. No finder, opportunities, league or v2 shared file changes here.

The existing package-contract and render Makefile lanes now exercise the selector too. Node checks cover three
counterparties, refreshed fit ranking, stable ties, cumulative slot/backup constraints, original ownership, input
immutability, missing values and sequential final rosters. Browser checks use the real helper and starter picker,
then render the selected package and changed final starters at 390 and 1280 px. This is isolated harness evidence,
not a live-site check. Earlier Makefile-wiring limits above are historical; PR 1161 supplied that wiring.

## On-demand panel and coordinator integration (2026-11-03)

`trade-package-panel.js` and `.css` add `TradeValuePackagePanel.mount(container)` / `mountBefore(target)`.
The returned controller accepts `update(snapshot)`. A completed snapshot is
`{status: "ready", league, candidates, ctx, capped?}` with the complete result and exact context described above.
The panel waits for **Build package**, computes the selection, and supplies the real `pickStarters` lineup adapter
to the existing preview. Stored roster slots never determine the lineup; FLEX and SUPERFLEX retain their actual
slot labels, and empty slots remain empty. The panel reports raw DDF gain across selected trades, separately from
the lineup. It explicitly describes greedy selection's limit and the unvalued K/DEF scope.

`update({status: "pending"})` immediately clears the old package and final lineup and disables Build package.
Each new completed snapshot also clears the previous selection. Reusing the identical completed snapshot preserves
the result and disclosure focus, so table filters/sorts do not destroy the user's package. No league roster is saved
or changed by building a package.

The shared-route owners retain `league.js` (#1084), `finder.js` (#1174), `v2.js` / shell (#1290), and the page builder
(#1084 / #1225). The unapplied `docs/integration/jeg1183-package-panel.patch` changes only league.js and the builder:
it loads/copies the assets, mounts the panel, retains the exact completed result context and roster copy, and clears
stale output when a new search is scheduled. It uses `result.rows` before any presentation filters, folds or pagination.
The patch applies cleanly to the recovery main integrated by this branch. The Node suite applies it to temporary
copies and verifies the builder's emitted script order and copied asset bytes; it never edits an owner's source.

Panel browser tests at 390/1280 px cover keyboard building, three distinct counterparties, the changed final starters,
same-snapshot preservation, pending invalidation, empty/unavailable results, touch size, overflow and unchanged inputs.
The full production-route test and live checks remain the coordinator's gate after applying the patch. This PR can
run full ready CI for its isolated component before that shared integration; it does not close JEG-1183 by itself.
