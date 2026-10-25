## 2026-10-25 - JEG-950: Compare verdict confidence needs 3 charts; "Value yes, market no"

Decisions (Jeremy, 2026-10-23, JEG-883 / JEG-950): (1) "High" on "Should you propose or accept?" needs at least 3
of the trade charts on the answer's side, else Medium; (2) keep "Toss-up"; (3) the value-win / market-lose deal read
is titled "Value yes, market no", with no call to action.

Changed: `app/v2/trade.js` (MIN_CHARTS_FOR_HIGH cap after the one-source step; the win|lose deal-read title, empty
action), a comment in `app/v2/v2.js`, tests, `docs/feature-contract.md` CT-02 and CT-08, `docs/risk-register.md`.
No extra reason line was added: the existing "N of M trade charts agree" line explains the lower level, and the
Compare card height is unchanged. `finder.js` does not reuse these labels.

Verified (ran): `tests/test_v2_headlines.py`, `test_v2_deal_read.py`, `test_v2_deal_read_chart_avg.py` (new cases
three-of-four, two-of-four, lose-two-of-four; two new mutations, "chart requirement removed" and "loosened to 2",
each fail the checks; the swapped-title mutation still fails); render tests one at a time:
`test_v2_compare_render.py`, `test_v2_deal_read_render.py`, `test_v2_compare_empty_side_render.py`,
`test_v2_contract_render.py`. A first try that added a "fewer than 3 trade charts agree" reason failed the render
test ("chart count must be its own line"); the reason was removed rather than the test changed.

Assertions changed, and why: anchors for `likely`, `arbitrage`, `zero-agree-wide` went from High to Medium and the
"Arbitrage: send it" title checks became "Value yes, market no". The rule they pin was changed by Jeremy.

Not run / assumed: the 12-combo sweep (no runnable script in this checkout and no build allowed); values are
assumed unchanged because the diff touches no value file (only the confidence cap and one label). The 1366x768
fit was not measured separately; the page gained no lines and the title is 2 characters longer on one line.
Where "Medium or Low" applies: the cap only lowers High to Medium; existing rules already give Low.
