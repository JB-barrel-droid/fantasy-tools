## 2026-10-31 - JEG-1217 Trade ideas: three Codex findings on 08bb633 (PR #1084)

Contract: fix the three Codex review findings without changing any value, fit or Trade opportunities number.

- P1, draft capital never had data: engine rows (curve-widget.js `buildCanonicalMap`) don't carry `preseason_ecr_rank`,
  and neither did `product-data.js` `getPlayers()`. `buildPlayers` now passes the field through as read-only data (no value
  reads it), and `manager-recs-ui.js` reads the ranks by `player_key` and passes them to `build` as `ranks`. A rank on the row
  itself still wins over the map. `curve-widget.js` and `dist/` are not touched.
- P2, your roster-construction failure was never shown: since JEG-1324, `ourFitOf` says "gains, roster issue" instead of
  "partial". `health()` now reads that label, and your own issues come from `fullFit`.
- P2, a failing own fit counted as a win: `ourFitOf` says "doesn't work" instead of "force". `isWin` now excludes that label.
  A trade that is force only because of the other side stays in.
- The harness now takes its "Our fit" labels from the real `opportunities.js` `ourFitOf`, so a renamed label fails the test.

Correction to 2026-10-30-jeg1217-trade-ideas.md: a reviewer saw at 08bb633 (with #1227's redraw on a scoring switch) that
Trade opportunities edges differ across Standard, Half PPR and PPR. The earlier "same under all three" note held only
before #1227.

### Verified (check named)
- `python3 -m unittest tests.test_jeg1217_manager_recs tests.test_jeg1217_manager_profiles`: 7 tests OK. That includes the new
  `test_draft_ranks_from_canonical_players` and `test_canonical_players_keep_the_preseason_rank`, plus mutations for each fix:
  the old "partial" label, the old "force" label, and canonical ranks ignored. Each mutation is caught.
- `python3 -m unittest tests.test_build_v2_page tests.test_product_data_wiring tests.test_source_combo_contract`: 13 OK.
- jsdom smoke in the scratchpad: engine rows with no rank, plus a stub `TradeValueProductData` with ranks. With draft marked
  "a lot", the idea is judged by preseason draft rankings (+20.0, Likely).

### Claimed, not confirmed
- The new render assertion (canonical ranks present, and this league's trades priced by the draft view) runs only in PR CI.
  There's no Chromium here.
