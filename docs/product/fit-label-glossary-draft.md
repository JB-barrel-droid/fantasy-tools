# Fit labels: glossary draft

Draft for Jeremy's review (JEG-1097). Nothing here publishes. Definitions are taken from the code at `origin/main` 06c9be24 (2026-10-25), not from memory. Where a definition depends on the two-DDF naming and defaults (JEG-1081) it is marked **provisional**.

**Note, 2026-10-26, design preview only.** Jeremy's labels for the Check a trade concept: the DDF read is DDF Charted Value and DDF Projected Value, side by side. Charted value starts from the trade charts. Projected value is the same method, starting from rest-of-season projections. Both are adjusted for position weight and the league's rosters. They are rooted in those inputs, not copied from them. The Market is a separate read: the trade charts before those adjustments, roughly how the other manager will see it. Each has a one-sentence (i). The shared terms below still say your view is DDF Value and their view is the trade chart average, which is what `origin/main` does. This note does not change the four fit rules or the live code. The preview is `docs/design/2026-10-direction.md`.

Sources read: `app/v2/finder.js` (`teamFit`, `tradeFit`, `fitText`, constants), `app/v2/opportunities.js` (`ourFitOf`, `theirFitOf`, `overallFit`, `FIT_WORD`, `TIERS`), `app/v2/league.js` (filter labels), `supabase/functions/mcp/viability.ts` and `docs/values-endpoint.md` ("Viability scoring").

## Finding: the name "Market Only Fit" does not exist

The code and the screen call it **Market fit** (`FIT_WORD.market = "Market fit"`, `opportunities.js` line 56). A header comment in the same file (line 7) says "market-only" and `docs/claude-log/2026-10-24-jeg-1021-league-workspace.md` follows that wording; the label a reader sees is "Market fit". Decide which name to use publicly. The glossary below uses "Market fit" because that is what ships.

Also: the finder card (`finder.js`, `fitText`) knows only three labels (Natural, Value, Force). Market fit exists only in the league trade-opportunities table (`opportunities.js`), where it is decided after the card rule. So a trade can read "Value fit" or "Natural fit" on a card yet "Market fit" in the table.

## Shared terms

- **Your view** = DDF Value (`ddf_value`). **Their view** = Trade chart average (`chart_avg`, mean of the compared charts, needs at least `MIN_CHARTS` = 3 charts). Each team is judged in the view it is assumed to use.
- **Net** for a team = change in best-lineup starter value plus the bench value at the engine's bench weight, after the trade minus before.
- **Noise floor** (tau) = max(0.05, FIT_Z x noise), `FIT_Z` = 1. Noise is the square root of the sum of squared per-player noise for every player moving. Per player: for DDF Value, half the gap between its trade-chart and projection versions; for the chart average, the standard error across the charts; for DDF Value (projections), the standard error across the projection sources. A net gain counts only if net > tau; a loss only if net < -tau; otherwise level.
- **Need** = distance from the expected depth band at QB, RB, WR, TE plus empty starting slots. Expected depth = league-wide rostered players at the position divided by teams, shown as a range (4.6 becomes 4-5). A player counts toward depth only if his value in that view is at least `USABLE_MIN` = 0.05. A trade moves a team **toward** depth if need after < need before, **away** if greater. Teams without a full set of starters are not judged on depth.
- A team is **served** when it gains and does not move away from depth, or when it is level and moves toward depth (a bench rebalance).

## The four labels

### Natural fit

- Plain: Both teams come out ahead in their own view, and the trade fixes a real depth need for at least one of them.
- Rule: your side served (in DDF Value, or in DDF Value (projections) when every player moving on your side has a projection value) AND their side served in the Trade chart average AND at least one served side moves toward depth in the view that serves it.
- Numbers: net > tau for each side (or level with depth moved toward), depth need after < before, tau at least 0.05.
- Variants: Natural fit (charts only) when only DDF Value serves you; Natural fit (projections only) when only the projections serve you. **Provisional:** the variants and which view counts as "yours" depend on JEG-1081.
- Table detail: in the opportunities table, also requires their depth to be "fills" (their side moves toward depth) to be natural; otherwise it drops to Value fit (`overallFit`, `theirLabel === "fills"`).

### Value fit

- Plain: Both teams come out ahead in their own view, but neither team's depth changes.
- Rule: both sides served and no side moves toward depth.
- Numbers: net > tau for both (or level-with-depth-move, which makes it natural instead), need unchanged for both.
- **Provisional** for the same reason as Natural (your view is DDF Value today).

### Market fit (asked as "Market Only Fit")

- Plain: You gain in your view and the trade would otherwise pass, but the trade charts show the other team losing, so it only works if they read the market differently.
- Rule (table only): your own label is not force, enough charts call it fair (`marketOk`), and the chart-average edge for them, as shown to one decimal, is below zero.
- Numbers: `marketOk` needs priced charts >= min(3, charts available) and charts with them winning or even >= min(3, charts available); chart edge = sum of chart average of what you give minus what you receive, rounded to 0.1, less than 0.
- **Provisional:** it is defined against the chart average, which is the Trade Charts view; follows JEG-1081 naming.
- Sort tier: third (`TIERS`: natural 0, value 1, market 2, force 3).

### Force fit

- Plain: At least one team loses, gains nothing measurable, or gains while making its roster worse balanced, or too few charts agree it is fair.
- Rule: on the card, your side not served or their side not served. In the table (`overallFit`), your side not served (`ourFitOf`), or `marketOk` false; the table does not look at whether their side is served in net terms, only at the chart edge and whether their depth fills, hurts or is neutral.
- Numbers: net < -tau, or |net| <= tau with no depth move toward, or net > tau while need increases; table: fewer than min(3, charts available) charts priced or with them winning/even.
- Shown last, with a one-click Hide force fits (league table). The card text lists why and, if one team gains only in the other view, says so.

## Where code and docs disagree

1. **Market fit vs "market-only"**: described above. Code label is Market fit.
2. **Three labels vs four**: `finder.js` header comment (lines 478 to 483) and `FIT_TIER` list three tiers; `opportunities.js` has four. Not a bug (different surfaces) but undocumented in `docs/v2-design-notes.md`; nothing there describes Market fit.
3. **Natural in the table vs on the card**: the card says natural when either served side moves toward depth (`fillsNeed = usToward || them.toward`); the table requires their side to fill (`theirFitOf` is "fills"). A trade natural on the card because only your depth moves is Value fit in the table. Confirm intent.
4. **Spec row 4 not implemented** (value when they would not accept): the JEG-1081 PR 2 log (`docs/claude-log/2026-10-25-jeg-1081-pr2-tri-view-fit.md`) says the spec table row contradicts the pinned rule that a team the market does not serve makes the trade force. Kept the pinned rule; decision for Jeremy. This directly affects the Market fit definition.
5. **Viability (MCP) uses different language and rules.** `mcp/viability.ts` and `docs/values-endpoint.md` label offers High, Med-High, Medium (acceptance likelihood) from nine checks; they never output Natural, Value, Market or Force. Check 3 and 4 need the lineup of each side to strictly improve (> 0), while the fit rule allows level-plus-depth-move and uses a noise floor. The assistant connector and the site can therefore rate the same trade differently. Not reconciled in docs.
6. **Table ignores their net.** `overallFit` never reads `fit.them.ok`. A trade the card calls Force because they lose (or gain nothing) can read Value or Natural in the table if the chart edge is not negative and enough charts call it fair. Confirm intent.
7. `values-endpoint.md` does not mention fit labels at all, so the plain definitions here have no doc home yet.

## Not verified

Rules read from source; I did not run the tests (`tests/test_v2_finder_fit.py`, `tests/test_v2_finder_trifit.py`) in this docs-only lane and did not run any real trade through both surfaces.
