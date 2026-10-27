## 2026-10-26 - JEG-950: "DDF Value likes it. The market doesn't." with the market-gap sub-line

Done by an OpenRouter deepseek-v4.1-flash run (T2/T3, untrusted until a Claude T1 review); the PM finished the
last steps (tests, log, commit) after the run hit its turn limit.

Decision (Jeremy, 2026-10-26 8:09 PM CT): the win|lose deal read (DDF Value win, Trade chart average lose) is titled
"DDF Value likes it. The market doesn't." with no call to action, replacing "Value yes, market no". Its live sub-line is
the real market gap: "Market has you down N points. Close the gap to land it.", N = |Trade chart average net| to
one decimal, the direction word from the net's sign (`marketGapWord` / `marketGapText` in `app/v2/trade.js`). The
grid cell's hover text stays static (no single net there). The JEG-886 split read and PR 920's confidence rule
(3+ charts High, 2 Medium, 0-1 Low) are unchanged. origin/main was merged in first (conflicts in
docs/feature-contract.md and tests/test_v2_deal_read_render.py resolved keeping both sides).

Changed: `app/v2/trade.js`, `tests/test_v2_deal_read.py`, `tests/test_v2_deal_read_chart_avg.py`,
`tests/test_v2_deal_read_render.py` (new 320px viewport, headline/sub-line box overflow check, a win|lose verdict
trade is always picked and checked), `docs/feature-contract.md` CT-08, `docs/research/posts/08-when-charts-agree.md`.
No CSS change: nothing overflowed at 320 or 390.

Verified (check named): test_v2_deal_read, test_v2_deal_read_split, test_v2_deal_read_chart_avg, test_v2_headlines,
test_v2_compare all OK; render, one at a time: test_v2_deal_read_render OK (after a fresh v2 build),
test_v2_deal_read_empty_side_render OK, test_v2_compare_empty_side_render OK, test_v2_contract_render OK.
Mutation: serving the old title makes test_v2_deal_read_render fail at 1440, 390 and 320 px; the
"hard-coded down word" mutation fails test_v2_deal_read. At 320 and 1440 px the rendered card read
"Market has you down 5.6 points. Close the gap to land it." with 0 px overflow.

Claimed, not confirmed: test_v2_compare_render fails on "Player values shown: duplicate option labels ['★ DDF Value']"
with and without this change (same failure with the branch's previous trade.js), so it is not caused by this work.
