## 2026-10-22 - JEG-841: Compare headline no longer contradicts Deal read on arbitrage trades

Contract: The "Should you propose or accept?" headline now uses DDF Value + DDF
Projections (not chart agreement) to decide the answer. This eliminates the
contradiction where the headline said "Unclear, 0 of 4 agree" while the Deal read
said "Arbitrage: send it" on the same screen.

### Changes

- `app/v2/trade.js` (`tradeHeadlines`): propose answer from DDF Value + DDF
  Projections (Yes when both win and margin 5%+; confidence from projections
  margin). Chart agreement count stays in the reasons sub-line for honesty.
  Added `fmtNet` helper for projections display.
- `app/v2/v2.js`: compute deal read before headlines; pass `deal` in ctx.
  Fixed doubled "Arbitrage: send it: Send it" label. Fixed N13 "fair-looking
  deal to them" copy that contradicted "Unlikely" verdict.
- `tests/test_v2_headlines.py`: rewritten for the new propose logic with
  regression fixtures including the four review trades (arbitrage, split,
  proj-missing, all-agree-win). Negative-tested via 6 mutations.
- `tests/test_v2_compare_render.py`: updated symbol set to include "?" for
  Unclear; removed stale headline-answer mutation (rendered test env has < 3
  charts, so propose is always Unclear); fixed pre-existing stale mutation.
- `tests/test_v2_deal_read.py`: fixed pre-existing stale mutation anchor
  ("no read without a market net" -> "no incomplete on too-few charts").

### Verified (check named)

- `test_v2_headlines.py`: 2 passed, 6 subtests passed (all anchors match,
  all 6 mutations caught).
- `test_v2_compare_render.py`: 3 passed, 3 subtests passed (rendered numbers
  match engine at 1440px and 390px).
- `test_v2_deal_read_render.py`: 4 passed, 4 subtests passed.
- `test_v2_deal_read_chart_avg.py`: passed.
- `test_v2_plain_copy_render.py`: passed.

### Claimed (not verified)

- The four specific review trades (Skattebo+Kincaid for Evans, Skattebo+Kincaid
  for Egbuka, Likely+Skattebo for Wilson, Jacobs+Montgomery for Brown) produce
  the correct headline on the live site. These are tested via unit test
  (`test_v2_headlines.py` arbitrage/zero-agree-wide cases) but not rendered
  against the live data since the rendered test env has < 3 charts.
