# JEG-1483 private starter contract: implementation and integration boundary

This lane owns the calculation/readout contract, tests and CI for JEG-1483.
The coordinator owns the full Fieldnotes UI and its already-readable authorized
baseline. No UI, baseline, sharing transport or Simplified adapter is edited here.
The prior Library transfer failure does not block this partitioned contract lane.

## Existing adapter, explicit adoption

`app/v2/trade-readout.js` extends the completed JEG-1230 API. Existing callers
without `calculationSettings` retain released behavior. The private next pass
opts into the approved contract through the same builder:

```js
const input = TradeValueReadout.inputFromContext(context, {
  rowsByKey, shape, chartKeys, sourceInfo,
  calculationSettings: {
    basis: "ddf_value", // or ddf_value_projections
    market: "published-average", // or usatoday, fantasypros, cbs, fantasycalc
    ourMinimum: {tier: "any"}, // noise or custom with value
    theirMinimum: {tier: "neutral"} // noise, gain, or custom with value
  }
});
const record = TradeValueReadout.build(input);
// record.decision: four ordered questions, label, supporting quantities.
// summary(record).decision: identical serializable record for parity checks.
// The same summary also retains views.market coverage/chartKeys/aggregation.
// Reuse the readout's compatible set for a compared package's MKT display:
const quote = TradeValueReadout.marketQuote(
  playerRow, record.decision.settings, record.views.market.chartKeys || []
);
```

The Simplified owner remains responsible for `app/v2/simplified-site.js` and
its PR1297 tests. None of those paths are touched here. Its eventual consumer
can pass the same calculation settings and render the shared decision; it
must not reconstruct a fit label from old weighted totals. Native finder
classification still needs integration into the full next pass. This opt-in
is not a claim that current Opportunities or Compare already uses the rule.
The coordinator should replace every private route label/count with this record,
then feed Simplified through its existing mount/getContext boundary.

## Four visible entries

Each entry names subject, scope, basis, source set/coverage, aggregation,
sign convention, measured value, known/unknown state and existing tolerance.
The numeric entry states its exact comparison operator and threshold. Legacy
`input.ourKey` cannot replace the selected canonical basis; it remains supported
only for unflagged released callers. Display-only input cannot reprice a verdict.

1. Our starters: positive change on the selected DDF Value/default or DDF
   Projections basis. Custom zero still means strictly positive.
2. Our construction: the existing `finder.rosterConstructionOk` on that basis.
3. Their starters: at least zero on the chosen market by default.
4. Their construction: the same existing roster check in their market view.

All four must pass for Natural fit. An unknown entry never becomes zero.
Projections and package totals remain supporting evidence unless projections
is selected as our basis. The noise tier uses the existing `teamFit().tau`,
including the existing 0.05 floor; no new numerical tier is introduced. Their
explicit noise tier permits the existing negative floor, while the default
does not. Their custom minimum can tighten or loosen that default.

`partnerKind: "waivers"` permits an add-only package and records questions3/4
as Not applicable: Waivers. Its type is Pickup, never Natural fit. No manager
readout, fictional lineup or roster limit is created. Unrelated unpriced free
agents do not remove known pickup sources. Deriving/importing the virtual
partner, stale-list handling and UI navigation remain to be integrated.

## One coverage definition

`PUBLISHED_CHARTS` is USA Today, FantasyPros and CBS. FantasyCalc is excluded
from that average and remains an explicitly selectable individual market.
`marketQuote(row, settings, availableKeys)` supplies the same per-player
coverage, zero/missing distinction, range endpoints and mean for Values and
Build. At0 sources it is unknown; at1 it returns the named individual value
and no average or fit availability; at2/3 it returns the arithmetic mean and
coverage2/3 or3/3. Zero is a value, not missing. Returned `inputs` reuse
`DDFSourceViews.read` ancestry: estimated, unlisted-zero and zero-listing-unknown
remain distinct, without changing the original indexed values or inferring
publisher listing from zero. The result also returns `status`, `sources`,
`fitAvailable`, `average`, `value`, and min/max endpoint source names in `range`.

For the roster readout, the compared rosters use one complete compatible
source set. A publisher missing a roster value does not join that average;
it cannot change one team's denominator without disclosure. An average with
fewer than two complete compatible sources is unavailable for judgment.
Explicitly choosing an individual chart/FantasyCalc uses its named1-of-1
setting under D7; this is distinct from a degraded1-of-3 average. The
coordinator should retain that distinction in UI copy and source controls.

Display columns are ignored by the decision. Market settings and basis are
calculation inputs. Their persistence, route invalidation and URL transport
must be supplied by the next-pass state integration; they are not implicitly
added to the older compact TradeContext transfer schema.

## Recomputed witness

The real witness uses the preserved v8 runtime's coherent Oct31/Week8 input
set, with current-main finder functions and the new adapter injected only for
calculation. It is **not** a browser review of the later design-next runtime.
Settings: Full PPR,12 teams, QB1/RB2/WR2/TE1/FLEX1/BN7, default modeled basis.
Jeremy's team gives Taylor547 + Tuten319 to Nic's team for Flowers1381 +
Hubbard4048. Source/module hashes and full selected inputs are in
`tests/fixtures/jeg1483-starter-real-witness.json`.

| Case | Our DDF starters | Their market starters | Our market package total | Construction |
| --- | ---: | ---: | ---: | --- |
| Three published sources | +3.3870498407 | +1.5478261163 | +6.5914810546 | Both pass |
| CBS unavailable,2 of3 | +3.3870498407 | +4.7078054496 | −2.0431097937 | Both pass |

The default four-entry rule classifies both pinned cases as Natural fit.
That conclusion follows the starter records, not the package arithmetic.
This is a private test oracle, not a fresh production claim.

## Verification and remaining integration

- New Node harness:62 contract assertions, including real pair/league/Compare
  context adapters and encoded TradeContext receive; no fake route-name loop.
- Python policy oracle independently checks the four comparisons and
  published-average composition. It consumes existing engine starter/roster/
  tolerance facts; it does not fork pricing, lineup selection or roster math.
  A32-case default/noise/custom/basis matrix also agrees across JS and Python.
- Existing JEG-1230 readout harness:319 assertions remain unchanged/passing.
- Combined Python run:5 tests. New tests are registered beside the existing
  readout unit command. Focused contract and CI-guard run:82 Python tests pass.
  No broad validation or release certification is claimed.
- Draft CI now runs the small starter/readout contract command in preview
  pr-state, separately from full builds/renders. Existing finalizers remain
  intentionally red while the PR is draft: run41738264652/job126273046901 shows
  RUN_EXPENSIVE=false, RENDER_RESULT=skipped, then the documented exit1. No render
  assertion failed. Do not weaken this gate or mark ready merely to make it green.

Coordinator integration still required: every page and H1–H13 handoff, real
Opportunities/Review/Edit/Buy-Sell adoption, source controls, Values markers/range,
full client-side compressed state replacement, calculation/week/league cache
invalidation, keyboard/focus and full desktop/phone journey checks. Legacy
TradeContext cache keys do not include the new settings: include the normalized
calculationSettings in the controller cache identity and shared payload.
Exact-head release CI and independent implementation review remain required.
No public rollout, Supabase, credential/access change or original-branch edit.

## Canonical candidate API (UI consumer)

Copy these three files from the same PR1302 head: `app/v2/finder.js`,
`app/v2/opportunities.js`, `app/v2/trade-readout.js`. Existing `source-views.js`
remains the provenance dependency; no UI or Simplified source is changed.

```js
const result = await TradeValueOpportunities.runCanonical(
  {id: myTeam.id, name: myTeam.name, entries: myTeam.entries},
  partners, // [{id, name, entries, partnerKind?: "waivers"}]
  {
    rowsByKey, // Map<string, original engine row>
    shape, charts: availableChartKeys, sourceInfo,
    calculationSettings, // same object/schema as readout input above
    maxSize: 2, week: actualDataWeek,
    excludedOpponentIds,
    constraint: target ? {direction: "buy", playerKey: target} : null
  },
  {limit: 20, offset: 0, fit: "all", isCancelled, onProgress}
);
const row = result.rows[0];
const decision = row.record; // exact canonical four questions + supporting data
const review = TradeValueOpportunities.canonicalReadout(row);
// review.decision equals row.record; it uses the captured pricing/roster inputs.
```

- `runAll` also delegates here when its ctx has calculationSettings. Do not
  canonical-rejudge output from legacy `findTrades`/`computePairing`: its early
  package edge/even-band/chart filters have already lost valid new-rule trades.
- `finder.enumeratePackages` reuses the bounded pool/subsets primitive. It has
  no legacy eligibility filters, automatic throw-in edits or projection gate.
  Each exact package is judged by the existing canonical builder. Unpriced
  known players are not silently removed. An explicit buy/sell target survives
  pool trimming when it belongs to that roster.
- `mine` and partner IDs are required and preserved. No manager/team identity
  is invented. For Waivers pass partnerKind on that supplied virtual partner;
  kind:"waivers" is also accepted, as is ctx.partnerKind for a single partner.
  The API does not derive a free-agent list or infer one from a partial league.
- Output rows carry id, opponentId/name, give/receive engine records, rank,
  `record` (canonical decision), and descriptive edge/score. `record.deal` and
  `record.participants` retain stable identities. Build/Review/Buy-Sell and
  Simplified must consume record values, not old fit, chart fairness or gain
  formulas. A known unbalanced package is not silently changed by a throw-in.
- `counts` is disjoint natural/other/unknown/pickup counts over all enumerated
  packages. `total` is the count matching the requested fit group; evaluated
  and totalPackages disclose computation. fit:"other" includes unknown cards.
- Pagination is applied only after canonical evaluation/ranking. limit is a
  positive finite integer (default existing finder LIMIT=10); offset defaults0.
  hasMore is explicit. This retains only the needed page prefix, not millions
  of full readouts. Increasing offset/limit reruns from coherent snapshots.
- Existing subset cap MAX_SUBSETS=6000 and opponent cap MAX_OPPONENTS=20 stay
  explicit through bounded/capped and perOpponent searched/of fields. Never
  claim an exhaustive full-league result when either flag is true.
- The existing tier/package-edge/complexity ranking is retained for known
  trade quantities, with Natural/Pickup before Other and unknown quantities
  never treated as zero. The old extra-player penalty gives no negative-extra
  bonus to an add-only Pickup. This does not introduce a new weight.
- Cancellation yields status:"cancelled", cancelled:true and rows:[]; no
  partial answer is published. Progress reports actual evaluated packages.
  There is no rounded legacy cache; every new run snapshots current inputs.
- `canonicalReadout(row)` works for a row returned by this module instance.
  It returns null for an unrelated/serialized row rather than fabricating its
  evidence. Shared links persist inputs/package and rebuild through the same
  readout; they do not serialize this private in-memory reference.
- A qualifying single-position Pickup can supply pickupAlternative on a trade
  row when its same-basis starter gain is at least that trade's gain. This is
  direct canonical evidence, not a manager-acceptance prediction.

`tests/node/jeg1483_candidate_check.cjs` proves recovery of a true starter fit
with negative DDF package total, projection-basis gains rejected by old DDF
filters, and positive gains below the old even band. It also checks complete
bounded enumeration, post-judgment paging, exact Review readout parity, target
constraints, exclusion preservation, missing-source unknowns, snapshot
immutability, cancellation, pool-cap disclosure and manager-free Pickups.

Final cancellation is checked again after the complete progress callback and
before publishing the page, so a superseding selection cannot leak an old result.
Pinned real candidate verification also enumerates all1440 Flowers-constrained
Jeremy/Nic size2 subset pairs and finds the documented Taylor/Tuten package,
with exact search-to-Review record equality. Full UI testing stays with its owner.
