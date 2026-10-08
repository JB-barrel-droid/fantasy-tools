# 2026-10-08 · v2 Compare a trade tab (frames 07 / 08)

Branch `fe/compare`. Front-end lane only.

## What changed

- `app/v2/trade.js` (new): `compareTrade(giveRows, receiveRows, series)`, one row per exact series,
  `net = sum(receive) − sum(give)`. A player missing a value in a series leaves that row with no sums
  and no net (null plus the missing players), never 0. The tab's only arithmetic.
- `app/v2/shell.html`, `app/v2/v2.js`, `app/v2/v2.css`: "Compare a trade" tab at `v2/#compare-trade`.
  Give / get cards with player search, a per-source result table (stacks as cards below 768 px), and a
  separate VORP vs waivers card. The Methods row (source selection) now shows on this tab too.
- `app/trade-value-chart/assets/curve-widget.js`: one read-only accessor,
  `TradeValueCurveControls.getAllRows()` (every priced player, ignoring the position filter, same
  value maps as `getRows()`). No engine math changed.
- `pipelines/build_v2_page.py`: ships and loads `v2/trade.js`.
- Tests: `tests/test_v2_compare.py` (added to `make test-core`), `tests/test_v2_compare_render.py`
  (added to `make test-unit`), `tests/test_build_v2_page.py` (trade.js loads before v2.js).
- `docs/v2-design-notes.md`: Compare a trade section.

## Verified (named checks)

- `make sync`, then `CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome make validate`
  exit 0 (cloud session, Linux; the macOS Chrome path does not exist here). The 7 skips in
  `tests.test_two_tier_frontend` are the same on origin/main.
- `tests.test_v2_compare`: sums, sign, real 0 counted, missing → no net, unpriced player missing
  everywhere. `test_checks_fail_on_broken_builds` fails on 4 mutated trade.js copies (sign flipped,
  missing read as 0, other series read, give side dropped).
- `tests.test_v2_compare_render`: headless dist/v2 at 1440 and 390, one Indexed and one VORP series
  turned on, trade built through the page's own search boxes (Gibbs + McCaffrey for Robinson + Ollie
  Gordon II on the current data). Every give / get / net equals the sum of
  `TradeValueCurveControls.getAllRows()` values; the missing-value row (no FantasyPros · DDA value for
  Ollie Gordon II) shows — plus a reason naming him; VORP only in its own card; trade survives a tab
  round trip; no page errors; no overflow at 390. `test_guard_fails_on_broken_builds` fails on sign
  flipped, missing read as 0, and VORP mixed into the trade-value table.
- `tests.test_v2_targets_render`, `tests.test_build_v2_page` still pass (Trade targets untouched).
- Screenshots at 1440 and 390 reviewed by eye.

## Claimed, not confirmed

- Layout matches frames 07/08: not checked. figma.com is blocked by this cloud session's network
  policy and the Figma MCP connector was avoided per instructions; the build follows the frame 22
  rule and frame 17 language. Frame node ids for 07/08 remain unmapped.
- Copy decisions made without Jeremy: title "Weigh a trade, source by source."; per-row labels
  "▲ you get more by this source" / "▼ you give more by this source" / "= even by this source".
  These are per source, not an overall verdict.
- The trade's sides are not saved across page reloads (module state only, like the other v2 state).
