# 2026-10-08 · v2 front end: Compare a trade waterfall and verdict (JEG-468 / JEG-469)

Branch `fe/agent-compare` (worktree `wt/agent-compare`), pushed to `main`.

## Verified

- `app/v2/trade.js`: new pure helpers `waterfall`, `waterfallScale`, `tradeVerdict`, `pickExample`;
  `tests/test_v2_waterfall.py` (added to Makefile test-core) pins step order and values, running
  totals, missing steps with no net, the shared scale from the cumulative extent, verdict kinds and
  "against" keys with incomplete rows ignored, and a deterministic example; 6 mutations all caught.
- `tests/test_v2_waterfall_render.py`, rendered against `getAllRows()` at 1440×900, 1366×768,
  1100×900 and 390×844: every step value and running total, landing = Receive − give, one shared
  scale equal to the largest cumulative extent, missing → hatched step and no landing, verdict
  headline series and sign with "Player values shown" set to a non-ranking series, disagreeing
  sources named, sides + verdict + verdict waterfall on screen without scrolling at 1440×900 and
  1366×768 with the table directly below, example marked and kept out of the address, no horizontal
  overflow. 6 broken-build mutations (per-row scale, verdict on the ranking series, verdict naming
  no source, no example, landing on incomplete rows, 3-column layout removed) all caught.
- `tests/test_v2_offer_render.py`: "complete rows have a bar" now looks for the landing bar
  (`.v2-wf-land`) instead of the removed `.v2-dbar` (rule changed by JEG-468).
- All `tests/test_v2_*_render.py` suites plus test_v2_compare, test_v2_trade_story and
  test_v2_waterfall pass (see commit message).
- Screenshots at 1440×900, 1366×768, 1100×900 and 390×844 (example, 2-for-2, missing value), light
  and dark, looked at by eye.

## Claimed, not confirmed

- The mobile verdict bar's hide-while-card-visible behaviour relies on IntersectionObserver; checked
  by eye at 390, not by a test.
- Tooltip placement near the viewport edges was checked by eye on desktop only.
