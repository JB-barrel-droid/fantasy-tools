## 2026-10-29 - JEG-1323 trade readout second half (verdict, will they accept, sell gap, data labels, context line)

Contract: add spec section 3.2's second-half rows to the shared readout (`app/v2/trade-readout.js`, JEG-1230 / #1088),
built only from what finder.js and team-summary.js already compute plus the #1084 band and #1105 league depth handed in
by the caller. No route is wired, so nothing on the page changes. No value math, rule, default or ranking changes.

Base: `claude/JEG-1230-trade-readout` at `b18c503` (#1088, still a draft). Branch `claude/JEG-1323`, stacked on it.

### What it adds

- `build()` now returns `readout.rows = {verdict, accept, sellGap, dataLabels, context}` (VERSION 2). New optional input:
  `fit {expected, weights, z?}`, `appeal` (#1084 rec: `{band, likelihood, why?}`), `leagueDepth`
  (#1105: `{check: {ok, reasons}, gapOf(key), floor?}`), `context {scoring, teams, superflex?, basis, benchLevel, week}`.
  `inputFromContext` fills `context` from TradeContext `common` and `pricing`, and passes `fit`/`appeal`/`leagueDepth` through.
- Verdict: `F.tradeFit` on the chart-average rows (league.js / finder.js `fitFor` call), `F.fitText`, and which of its
  three tests failed. Unavailable with S13 under 3 charts, or when the league's expected depth is unknown.
- Will they accept: the #1084 band when a valid one is passed; otherwise `F.viabilityLabel` (league.js call, chart-average
  rows) and `F.evaluateCombo`'s charts-even count, with held charts named.
- Sell gap: per moving player, `TradeValueTeamSummary.marketGaps` gap (DDF Value minus Trade chart average), a lean named
  only above `NOISE_FLOOR` (2.0); #1105 league depth only when its check passes, with its reasons listed when it does not.
- Data labels per team (each player once, on his roster before the trade): S8, S9, S10, "◐ 1 source", "≈ estimated",
  and the Overrides badge text.
- Context line: "Full PPR · 12 teams · 1QB · DDF Value basis · Standard bench · Week 8"; unknown parts listed as missing.
- `renderRows(readout)` draws the five rows in the spec's order, each with its value or its reason.

### Verified (check named)

- `node tests/node/jeg1323_trade_readout_rows_check.cjs`: 67 checks passed. Golden trade (12 teams Full PPR, CBS held, a
  kicker, a player with no engine row, a throw-in with no FantasyPros value, a single-source player, an estimated chart
  value, an override) pinned in `tests/fixtures/jeg1323_trade_readout_rows_golden.json`; verdict and acceptance equal the
  league finder's own `tradeFit` / `viabilityLabel` / `evaluateCombo` calls; sell gaps equal `marketGaps`.
- Fails without the change: on the #1088 head the check stops at "the readout carries the second-half rows (JEG-1323)".
  Mutations caught: league depth used past a failed check; no noise floor; fit on rows without the chart average; the
  kicker label dropped; a roster player skipped.
- Weekly values on the rows do not change any second-half row (named case).
- `node tests/node/jeg1230_trade_readout_check.cjs`: 315 checks passed (first half unchanged).
- `make validate`: build OK, `make test-core` 70 modules OK, then `tests.test_week_history` errors on `No module named
  'playwright'` (this environment), as on #1088.

### Claimed, not confirmed

- The pair finder (finder.js `viabilityFor`) passes give/receive rows without the chart average to `viabilityLabel`,
  while league.js passes chart-average rows. The readout follows league.js. Read from source only; JEG-1326's parity
  test should pin which one the finders show.
- Copy composed from existing words, pending review: the context line wording ("DDF Value basis", "Standard bench",
  "Bench from your league's rosters", "1QB"), the sell-gap lines and the no-viability line.
- Browser render of `renderRows` not checked here (no Chromium); the node check uses a minimal fake document.
