# JEG-1483 private starter contract: implementation and integration boundary

This is the calculation slice of the reconciled JEG-1209 brief, not completion
of the full design. The later real-runtime source transfer is blocked. No new
UI, publication, shared-state replacement or Simplified adapter is activated.

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
```

The Simplified owner remains responsible for `app/v2/simplified-site.js` and
its PR1297 tests. None of those paths are touched here. Its eventual consumer
can pass the same calculation settings and render the shared decision; it
must not reconstruct a fit label from old weighted totals. Native finder
classification still needs integration into the full next pass. This opt-in
is not a claim that current Opportunities or Compare already uses the rule.

## Four visible entries

Each entry names subject, scope, basis, source set/coverage, aggregation,
sign convention, measured value, known/unknown state and existing tolerance.
The numeric entry states its exact comparison operator and threshold.

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
readout or acceptance prediction is created. Deriving/importing the virtual
partner, stale-list handling and UI navigation remain to be integrated.

## One coverage definition

`PUBLISHED_CHARTS` is USA Today, FantasyPros and CBS. FantasyCalc is excluded
from that average and remains an explicitly selectable individual market.
`marketQuote(row, settings, availableKeys)` supplies the same per-player
coverage, zero/missing distinction, range endpoints and mean for Values and
Build. At0 sources it is unknown; at1 it returns the named individual value
and no average or fit availability; at2/3 it returns the arithmetic mean and
coverage2/3 or3/3. Zero is a value, not missing.

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

- New Node harness:52 contract assertions, including real pair/league/Compare
  context adapters and encoded TradeContext receive; no fake route-name loop.
- Python policy oracle independently checks the four comparisons and
  published-average composition. It consumes existing engine starter/roster/
  tolerance facts; it does not fork pricing, lineup selection or roster math.
- Existing JEG-1230 readout harness:319 assertions remain unchanged/passing.
- Combined Python run:5 tests. New tests are registered beside the existing
  readout unit command. No broad validation or release certification is claimed.

Still required: latest baseline materialization/pixel inspection, every page
and H1–H13 handoff, real Opportunities/Review/Edit/Buy-Sell adoption, source
controls, Values markers/range, full client-side compressed state replacement,
partial/missing/reset/week invalidation, keyboard/focus and full desktop/phone
journey checks, exact-head release CI and independent implementation review.
No public rollout, Supabase, credential/access change or original-branch edit.
