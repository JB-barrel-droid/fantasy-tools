## 2026-10-22 - JEG-820 Trade targets: rank by weighted gap, 5-point Sell floor

- Problem (product review 2026-10-22 item 2): Sell top 5 were 0.0 to 3.4 bench
  or waiver players ranked by raw consensus gap (Boston 1.2 vs 14.6, Corum 0.0
  "Drop"); Buy was the overall top 8.
- Where the ranking lives: `app/v2/targets.js` only (pure front-end functions
  over the engine's rows). No value math, no engine or Python reference
  involved; the test pairs with `tests/test_v2_targets.py`.
- Fix (ticket option B, proceeding per standing instruction; Jeremy to confirm):
  `market.weight = min(ours, consensus)`, `market.score = |gap| x weight`; both
  lists sort by score, Sell also needs `ours >= SELL_FLOOR` (5). Players under
  the floor are counted (`belowSellFloor`) and said in the footnote. A second
  footnote says when DDF Value rests on one source for a listed player (leads,
  not verdicts). Meta line: "biggest gap first, weighted by the value at stake".
- Before / after on the 2026-10-22 build (USA Today + FantasyPros compared, DDF
  Value from 2 sources), measured with `window.TradeValueV2.targets()` headless:
  - Full PPR 12 (default). Sell before: Wan'Dale Robinson 1.1 vs 7.3, Deebo
    Samuel 2.0 vs 8.1, Omar Cooper 1.1 vs 7.1, Charbonnet 2.7 vs 8.7, Emanuel
    Wilson 2.5 vs 8.5. After: Skattebo 9.5 vs 13.0, Jordan Mason 9.6 vs 13.1,
    Hampton 9.3 vs 12.8, Woody Marks 10.6 vs 13.7, Etienne 9.4 vs 12.7. Buy
    before: JSN, Nacua, Gibbs, Chase, Bijan, Walker, St. Brown, Allen. After:
    Gibbs, JSN, Nacua, Bijan, Walker, Chase, St. Brown, Cook.
  - Standard 10. Sell before: McConkey 2.2 vs 10.4, Harrison 0.7 vs 8.9, Waddle
    3.4 vs 11.2, Bernard 3.3 vs 11.0, Odunze 2.8 vs 10.4. After: Burden 8.9 vs
    14.2, Egbuka 8.8 vs 14.2, Jameson Williams 9.3 vs 14.3, DeVonta Smith 11.9
    vs 15.6, Coker 12.1 vs 15.7. Buy: top RBs before and after (Gibbs, Bijan,
    Walker, Cook, Taylor ...).
  - Half PPR 8. Sell before: McConkey 0.8 vs 8.4, Waddle 1.7 vs 9.0, Boston 2.0
    vs 9.2, Bernard 1.7 vs 8.8, Odunze 1.4 vs 8.4. After: Burden 6.4 vs 11.4,
    Egbuka 6.2 vs 11.3, Jameson Williams 6.5 vs 11.1, DeVonta Smith 9.7 vs
    12.5, Ollie Gordon 7.3 vs 10.9. Buy: Gibbs, Bijan, Walker, JSN, Nacua ...
- Buy side finding: ours / consensus among Buy targets is 1.3 to 1.5 in every
  consensus bucket (Full PPR 12: 1.39 / 1.39 / 1.30 / 1.43 / 1.43), so the Buy
  list is the scale gap, not per-player mispricing; option B equals the current
  list there and no gap ordering does better. Logged as MR-28 in
  `docs/math-review-agenda.md` and GAP-TARGETS-BUY-SCALE-EFFECT in
  `docs/risk-register.md`.
- Verified: `python3 -m unittest tests.test_v2_targets` green with 8 new
  mutations (floor removed / strict / moved / applied to Buy, weight dropped,
  max instead of min, ascending score, floor count dropped) each caught; the
  same checks against origin/main's targets.js give 10 errors (fails without
  the fix). `tests.test_v2_targets_render` green (RENDER_TESTS_REQUIRED=1) with
  two new JEG-820 mutations caught; its one-source probe moved from 0.5 to 5.5
  to stay above the floor. `make validate`: see the PR.
- Not run: the 12-combo sweep. `curve-widget.js` / `value-model.js` untouched;
  the engine dump on this branch is the same code as main.
