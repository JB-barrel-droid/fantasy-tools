## 2026-10-25 - JEG-950: Compare verdict confidence needs 3 charts; "Value yes, market no"

Decisions (Jeremy, 2026-10-23, JEG-883 / JEG-950): (1) "High" on "Should you propose or accept?" needs at least 3
of the trade charts on the answer's side; follow-up 2026-10-25: 2 charts cap the level at Medium, 0 or 1 cap it at Low; (2) keep "Toss-up"; (3) the value-win / market-lose deal read
is titled "Value yes, market no", with no call to action.

Changed: `app/v2/trade.js` (MIN_CHARTS_FOR_HIGH cap after the one-source step; the win|lose deal-read title, empty
action), a comment in `app/v2/v2.js`, tests, `docs/feature-contract.md` CT-02 and CT-08, `docs/risk-register.md`.
No extra reason line was added: the existing "N of M trade charts agree" line explains the lower level, and the
Compare card height is unchanged. `finder.js` does not reuse these labels.

Verified (ran): `tests/test_v2_headlines.py`, `test_v2_deal_read.py`, `test_v2_deal_read_chart_avg.py` (new cases
1, 2 and 3 of 4 charts on both sides; mutations "chart requirement removed", "loosened to 2", "one chart only caps at
Medium" and "two charts not capped" each fail the checks; the swapped-title mutation still fails); render tests one at a time:
`test_v2_compare_render.py`, `test_v2_deal_read_render.py`, `test_v2_compare_empty_side_render.py`,
`test_v2_contract_render.py`. A first try that added a "fewer than 3 trade charts agree" reason failed the render
test ("chart count must be its own line"); the reason was removed rather than the test changed.

Assertions changed, and why: anchors for `likely`, `arbitrage`, `zero-agree-wide` went from High to Medium and the
"Arbitrage: send it" title checks became "Value yes, market no". The rule they pin was changed by Jeremy.

Not run / assumed: the 12-combo sweep (no runnable script in this checkout and no build allowed); values are
assumed unchanged because the diff touches no value file (only the confidence cap and one label). The 1366x768
fit was not measured separately; the page gained no lines and the title is 2 characters longer on one line.
Caps only lower a level, never raise it (a one-source Low stays Low). Owner confirmed by Jeremy 2026-10-25: session:fe-pc.

Second pass (2026-10-25): anchors for likely, arbitrage and zero-agree-wide are now Low (0 or 1 chart agrees); the unit and render files were rerun one at a time after the change (headlines, deal_read, compare_render, deal_read_render). The contract render test was run on the first pass only and not rerun.

Third pass (2026-10-25), on head 1885bb02 (after the Low rule): `tests/test_v2_contract_render.py` 6 passed and `tests/test_v2_compare_empty_side_render.py` 2 passed, each run alone. No test was changed.
