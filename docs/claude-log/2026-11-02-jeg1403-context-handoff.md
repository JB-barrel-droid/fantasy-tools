## 2026-11-02 - JEG-1403 league-to-Compare context handoff

Contract: continue PR #1277's finder-only one-chart gate and repair the two exposed journey failures without changing value calculations. Work stays on `claude/JEG-1403-finder-one-chart`; the parent coordinator owns independent review and merge.

### Verified (check named)
- GitHub PR/ticket history and the operations snapshot: prior implementation head `5e8f3cf6` was unchanged, the previous Mac writer was stopped, and no current implementation claim existed. Claimed takeover on JEG-1403 before editing.
- Normal merge of current `origin/main` (`6408b9b8`) into the existing PR branch completed without conflicts.
- Reused shared front-door identity fix `be2cb8cd19fce2cfa09101dd5b299c85b266c907` by cherry-pick (`81ef8ecb`), rather than duplicating it. The org-cutover build uses the configured destination identity; the prior test pinned the former owner's URL.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_uso_site_journey_render` before the repair: 18 tests, exactly two failures (`test_journey_keeps_the_trade_context`, `test_unequal_deal_keeps_its_package`), including opponent substitution and missing gains/readout. No journey assertion changed.
- `python -m unittest tests.test_jeg1229_trade_context tests.test_v2_finder tests.test_v2_finder_search_unchanged`: 6 tests passed before the producer repair.
- Source trace: Compare already receives and validates `tc=` via `TradeValueTradeContext.receive`; `league.js` sent only `give`/`get`. The repair sends the selected teams, deal, complete value context, league settings and existing modeled pricing identity. The existing league-pricing hold remains.
- Unchanged post-repair journey suite (same Chromium command, verbose runner): 18 tests, one failure. `test_unequal_deal_keeps_its_package` and the `get=` mutation guard now pass; every league-to-Compare and Compare-reload stage retains rosters, values, gains and readout. The remaining failure is `Compare elsewhere` on the foreign device.
- `python -m unittest tests.test_jeg1188_opportunity_count tests.test_league_levels_trades`: 12 tests passed.
- Remaining failure traced to `app/v2/v2.js` `tradeHash()`: serializing a carried trade retains `tc=` but omits `valuecontext=1`. Default basis is omitted by `shareParams()`, so the foreign device retains its saved FantasyCalc basis and `receive()` correctly holds the mismatch. JEG-1403 explicitly requires stopping/reporting before editing `v2.js`, and PR1084 is a separate active lane. The coordinator must allocate this follow-up; no `v2.js` edit was made here.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_jeg1249_league_site_render`: 4 tests run, 2 subtest failures in `test_league_to_compare_journey`. The new complete link causes `applyLinkLeague()` to announce settings and `league.js` `onSettingsChanged()` persists a settings snapshot (`null` becomes the current state/shape), violating that regression's unchanged-saved-workspace assertion. The pricing hold checks pass. This is a second outstanding integration requirement: link-only settings must refresh the visit without persisting the reader's workspace. The existing event does not identify persistence intent; its source needs coordination with the same protected `v2.js` lane. No assertion was weakened and no speculative listener workaround was added.

### Claimed, not confirmed
- `make validate` and terminal CI are pending in this session.
- The required follow-up is to emit `valuecontext=1` alongside `tc=` when `tradeHash()` serializes a carried trade. It has not been applied or tested here because of the explicit code-path boundary. The journey stays on `KNOWN_RED` until all 18 pass.
- Merge and live verification belong to the parent coordinator; this session does not merge or deploy.

Runtime note: `.agents/skills` is absent in this checkout. Shared Linear field notes could not load (`get_agent_context` backend reports tool not found). The cloud runtime skill and current repository instructions were read. The first browser build needed the explicit installed `CHROMIUM_PATH`; the Playwright browser-cache revision is absent.
