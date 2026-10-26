## 2026-10-26 - Connector fit label (JEG-1115)

Contract: trades returned by the connector (`supabase/functions/mcp`) carry the same fit
label the finder, the league table and the detail panel show (Natural / Market supported /
Force), next to viability (High / Med-High / Medium), with a plain-English reason. Split
from JEG-1108; the rule itself is not changed.

This run was an OpenRouter **deepseek-v4.1-flash** headless run (T2/T3). Its output is
untrusted until a Claude T1 review.

### What changed

- `supabase/functions/mcp/fit.ts` (new): the shared fit module. It never reimplements the
  rule — it calls the site's own `TradeValueFinder.tradeFit` and `fitText`
  (`app/v2/finder.js`, JEG-1108) exactly as the page's `fitFor()` does, and maps the label
  to its display words. `FIT_Z`, `MIN_CHARTS`, `MARKET_KEY`, `OUR_KEY`, `CHART_KEYS` are
  read from the finder, never copied. Also holds `benchWeightsFromPlayers` (below) and
  `buildFitContext`.
- `supabase/functions/mcp/find-trades.ts`: `TradeCandidate` gains `fit` and `fit_reason`;
  `FindTradesOpts` gains `fit` (a fit context). `findTradesForPair` judges each trade with
  `fitForTrade` when a context is given, else leaves both null.
- `supabase/functions/mcp/viability.ts`: `TradeOfferInput` / `ScoredOffer` carry the fit
  label through `scoreAndRankOffers` unchanged (pass-through fields only; no check, ranking
  or label changed).
- `supabase/functions/mcp/tools.ts`: both finder tools build the context
  (`fitContextFor`) and show the label in the text answer (`Fit: Natural — …`) and in the
  structured `trades` output. Tool descriptions now list the fit label as an output field.
- Tests: `tests/node/connector_fit_check.mjs` (new) + a runner in `tests/test_mcp_remote.py`;
  `tests/node/mcp_remote_check.mjs` asserts the handler's output carries fit + fit_reason.
- `.gitignore`: `tests/node/.fit_build/` (the esbuild build dir, mirroring the existing
  `.viability_build/` line). Deliberate one-line deviation from the ticket's file list, so
  the generated dir is not committed.

### Verified (check named)

- `node tests/node/connector_fit_check.mjs` → `ok`. It checks, on the 20-team fixture league
  (`tests/fixtures/league/fixture-20team.json`, team 0 = you):
  - **parity**: for every trade `finder.findTrades` returns, the connector's label equals
    `FIT_LABELS[finder.tradeFit(...).label]` and `fit_reason` equals `finder.fitText(...)`
    on the same inputs — 189 trades, 0 mismatches;
  - the same rows `tests/node/fit_diagnostic.cjs` counts: the connector's label equals each
    opportunity row's `overall` fit, row for row (189 rows);
  - the fixture separates the labels (Natural 61, Market supported 86, Force 42 — the same
    split `node tests/node/fit_diagnostic.cjs` prints);
  - `findTradesForPair` output carries a label and a reason for every trade; with no
    context both are null.
- **Mutant (failing-first)**: stubbing the fit attach out of `find-trades.ts`
  (`const fit = { fit: null, fit_reason: null };`) makes the check fail on the
  "trade carries a fit label" assertion; restoring it makes it pass. The committed test also
  bundles that mutated source and asserts the same check throws on its output.
- `node tests/node/fit_diagnostic.cjs --assert` → assertions passed (61 / 86 / 42 of 189).
- `node tests/node/viability_check.mjs` → 28 passed, 0 failed (the pass-through fields do
  not disturb scoring).
- `npx node@22 --experimental-strip-types tests/node/mcp_remote_check.mjs` → `ok`
  (handler-level: every find_trades trade has fit + fit_reason, the text shows `Fit: …`,
  "Value" never appears).
- `npx node@22 --experimental-strip-types tests/node/batch_trade_check.mjs` → all passed.
- `python -m unittest tests.test_edge_functions_parse` → OK (skipped=1, deno absent).
- `python -m unittest tests.test_mcp_remote` → `test_connector_fit_label` and
  `test_function_is_public_like_get_values` pass; `test_dispatch_and_tools` and
  `test_batch_trade_discovery` fail locally with `node: bad option:
  --experimental-strip-types` because this box's node is v20 (they need v22+; both pass
  under `npx node@22`, and they are unchanged by this work).

### Claimed, not confirmed

- **The bench-share weights are the one input the connector cannot get faithfully.**
  `tradeFit` weights the bench half of your DDF Value total by the engine's bench-share
  readout (per position), which the site reads from
  `TradeValueCurveControls.getBenchShareReadout()` — an output of the value pipeline
  (`app/trade-value-chart/assets/value-model.js`, ES-14). `get-values` does not return it.
  The connector reads it back from what `get-values` does publish (each player's blended
  value and the engine's own `tier`) in `benchWeightsFromPlayers`. The engine walks the
  bench slice in projected-points order (meanPpg) while `tier` is assigned on the
  blended-value order, so the two can differ at the boundary; the clean fix is a
  `get-values` change to expose the readout (out of this ticket's scope). Measured on the
  fixture: per-position weights 61/86/42 vs an empty weights object 51/84/54 — the weights
  move labels, so this matters and needs T1 eyes.
- `expected` (engine expected depth) is null in the connector context: it only drops the
  depth sentence from `fit_reason` and never moves the label.
- No live/edge-function run: nothing was deployed, no Supabase call was made (per the
  ticket and the lane rules). The connector's fit has not been checked against a real
  published league.
- `make validate` / render tests were not run (no value math, engine, config or published
  output changed).
