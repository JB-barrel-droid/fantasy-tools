## 2026-10-26 - JEG-1108: your side of Natural fit needs any rise

Contract: apply Jeremy's decision (2026-10-26): your side of Natural fit is "DDF Value total roster value rises (any rise), starters not worse"; the noise floor stays on the other team's side. No other threshold changed.

### Change
- app/v2/finder.js tradeFit: `yourTotalUp` was `us.net > us.tau` (noise floor), now `us.net > NET_FLOOR` (0.05, the smallest change the page displays as non-zero; Jeremy's option B read "above +0.05"). The "does not rise" wording no longer cites a noise floor. Their side (`theirOk`, `marketSupported`) untouched.

### Tests, per test
- tests/test_v2_finder_fit.py tests 1-11: unchanged, all still pass (none pinned the old your-side noise rule; test 11 pins their-side noise scaling and still does).
- New test 12: a rise of +0.45 with your noise floor about 14 is natural. Fails on the old rule.
- New test 13: a rise of +0.03 is not natural (guards against "any rise" turning into "no test").
- New mutants: "your side needs the noise floor" (restores the old rule; caught by test 12) and "your side needs no rise" (caught by test 13 and the drop tests).
- tests/test_v2_finder_trifit.py and test_v2_league_units.py: unchanged, pass.

### Distribution (20-team reference league)
| Label | Synthetic engine rows, 189 opportunities, before -> after | Real page, real engine values, 89 opportunities, before -> after |
|---|---|---|
| Natural | 55 (29.1%) -> 55 (29.1%) | 4 (4.5%) -> 60 (67.4%) |
| Market supported | 97 (51.3%) -> 97 (51.3%) | 0 -> 0 |
| Force | 37 (19.6%) -> 37 (19.6%) | 85 (95.5%) -> 29 (32.6%) |

Real page per test: roster construction passes for both teams on 64; their side within noise or better on 87; your total rises with starters not worse on 84 (was 6); construction and your side together 60.
Natural on the real page is now above the 60 percent line set for this lane, so the question went to Jeremy as multiple choice; task 2 and 3 not started.

### Verified (check named)
- `node tests/node/fit_diagnostic.cjs --assert`: 55 / 97 / 37, assertions pass.
- `python -m unittest tests.test_v2_finder_fit tests.test_v2_finder_trifit tests.test_v2_league_units`: pass, including mutant checks.
- Real page: scripted check (seed 20team via tests/_league_render, count `TradeValueLeague.ui.result.rows` by `overall`): 60 / 0 / 29.

### Claimed, not confirmed
- Synthetic is unchanged because its engine rows already clear the noise floor on your side.
