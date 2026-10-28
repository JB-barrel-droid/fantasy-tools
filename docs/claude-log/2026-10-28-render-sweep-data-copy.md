## 2026-10-28 - Render sweep: four stale render tests (values tab, finder paste, basis baseline, overrides rubric)

Contract: diagnose four render-sweep failures on main and fix each in the test where the test, not the page, is stale. No app, engine, data or dist change. Branch `fix/sweep-data`. No browser in this environment (Playwright install blocked), so the render tests were not run; root causes were reproduced in Node by loading the real engine (`value-model.js`, `product-data.js`, `curve-widget.js`) with the fake DOM from `tools/guard_harness.mjs`, serving the built `dist/assets`.

### Changed
- `tests/test_v2_finder_paste_render.py`: the paste help must say "stays on this device". 13edf364 (JEG-1130, approved PMM launch copy, Jeremy 2026-10-26) changed the copy from "stays in this browser", and `tests/test_launch_copy_guard.py` now forbids the old phrase.
- `tests/test_v2_values_tab_ux_render.py`: the no-blank-row check needs a player a selected source leaves unpriced. Since 679fa54e (JEG-1073) DDF Value is the trade-chart average and every chart is filled, so the default selection prices all 738 listed players. When it finds no gap, the check now selects one DDF Value version and one publisher series that the most-gapped player lacks (today DDF Value (projections) and ESPN; Tyreek Hill), through `TradeValueV2.setShown`, and asserts as before. New mutation "a publisher row with no number" covers the publisher row builder. Page clock pinned to the data's week (JEG-1152 pattern).
- `tests/fixtures/baseline_main_61ecb39e/` renamed to `baseline_main_771c3422/` and re-frozen: the two engine files are now origin/main's at 771c3422 (last engine change 4c17ee6b), byte for byte; README says why and how to re-freeze. `tests/test_basis_overrides_render.py` points at it.
- `tests/test_v2_overrides_basis_render.py`: rubric item 10 reads the Compare verdict's title and text (`verdict_of`), not the text alone.

### Verified (check named)
- Values tab: Node probe at the default selection, DDF Value + four charts: 2 unpriced players (Joe Mixon, Tyreek Hill, DDF Value) with the engine at 679fa54e^ and 0 at 679fa54e, on the same fixture (a0601351's data); 0 on main's data and engine. Projections leave gaps (ESPN 145, CBS ROS 372, Razzball 106, DDF Value (projections) 2); the selection rule picks DDF Value (projections) + ESPN, Tyreek Hill.
- Basis baseline: Node snapshot (the test's SNAPSHOT fields, 12 combos, clock pinned to 2026-10-26) of the 61ecb39e copies vs each main engine commit since 679fa54e: identical through d377e659, 150-310 players differ per combo from the JEG-1121 bench-seat commits (#957, 47fd50ca) on. On main's engine, setBasis(null), {mode: "default"} and the equal four-chart blend equal the default in all 12 combos. The three Broken* mutation anchors are present in main's engine.
- Overrides item 10: Node probe, built dist, 12 teams PPR: RB #4 James Cook 52.38, WR #4 Amon-Ra St. Brown 51.64; DDF Value net -0.74 (lose) before, about -28.4 (override clamped to 80) or -40.8 (unclamped) after; FantasyCalc +5.18 and CBS +2.31 (you win) both times, so `verdictCopy`'s text is identical and only the title's net moves.
- Finder: `python3 -m unittest tests.test_launch_copy_guard` OK; the seven finder mutation anchors are present in `app/v2/finder.js`.
- `python3 -m unittest tests.test_basis_overrides tests.test_no_real_clock tests.test_launch_copy_guard` OK.
- This branch merges into origin/banana/jeg-1135-render-sweep without conflict (`git merge --no-commit`, then aborted).

### Claimed, not confirmed
- The four render tests pass in CI. Not run here (no browser); the reasoning above is from Node with the same engine, not from Chromium.
- `test_ten_rubric_items` on main alone still fails at item 5: since JEG-1073 the blend starts on the four charts, so `#v2OvW-espn` is disabled and `page.fill` times out. The open PR banana/jeg-1135-render-sweep ticks ESPN first; item 10 needs both. Its `set_player_override` clamp to the slider max is not needed on main since bf7ac7b1 (the slider grows with the value) but is harmless.
- The basis test is now a regression lock on main's default path since 771c3422, not a proof that the basis feature left the pre-basis engine untouched (JEG-1044 is merged). Each later deliberate default-value change has to re-freeze it.
