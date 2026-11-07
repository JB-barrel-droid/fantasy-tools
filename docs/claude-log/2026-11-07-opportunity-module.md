## 2026-11-07 - JEG-1558 opportunity module (part 1 of 2: ddf-opportunity.js)

Contract: one module that every surface uses to size a move. It gives the team page's opportunity tier
(big / medium / marginal / none) and the roster-improvement percent for the sender and the partner of a trade
(Why panel JEG-1561, trade messages JEG-1559). The value model is unchanged: the module only reads TradeValueFinder
(lineupValue, benchWeight, withChartAverage) on the engine's rows.

Decisions (Jeremy, 2026-11-07, multiple choice): thresholds 3 / 6 / 10% of team worth plus the noise rule; trades
count only when they fit both rosters (tradeFit "natural"); the roster hole shows as "where to look" outside the tier;
ship on this snapshot. Also: "trade improvements ... should also be framed as a % ('your roster gets x% better')", and
a signed percent for the partner with plain bands (better / essentially unchanged / slightly worse / clearly worse).

Why this denominator: worth (starters in full, bench at the engine's bench weights) is the same number the Waivers tab
and tradeFit already count, so the tier and the trade card agree. On the 36 rosters of the phase 1 experiment
(three Yahoo half-PPR 12-team leagues, week 9; aggregates only, in the handoff folder
06-audit/opportunity-size-experiment-2026-11-07.md), the best natural trade's percent had a median of 6.6% over worth,
6.6% over starters-only value and 6.1% over the roster's value above waivers. The three bases were nearly the same
because DDF Value is already priced above the waiver line. The smallest base was 117 points, so no tiny-base inflation.
League-rank scale ("places") is not a percent of the roster; it is kept only in the tier wording. A base under 20 points
gives no percent (guard for partial pastes).

Why the partner bands: on the same 36 best natural trades the partner's change (Analyst charts, the find page's
"their valuation") ran from −5.8% to +1.1% (median −1.0%). Half fell within ±1% and the next third between −1% and
−3%. The engine's noise floor is about 2.5% of a roster (median), too wide to call "unchanged", so the band is ±1%.
3% matches the "no meaningful opportunity" line on the gain side.

Caveat (Jeremy asked for this note): the thresholds and bands come from ONE week of THREE Yahoo half-PPR 12-team
leagues. Re-check them on superflex and full-PPR leagues: JEG-1562.

### Verified (check named)
- Tier boundaries 2.9 / 3.0 / 5.99 / 6.0 / 9.99 / 10.0, band boundaries +1 / −1 / −3, display truncation, noise rule,
  waiver vs trade source, tiny-base guard, sender/partner symmetry, zero change not signed: `tests.test_ddf_opportunity`
  (11 tests, node).
- worth() equals waivers.js netOf(lineupValue(...)), and the sender delta equals finder.js teamFit's net on the same
  synthetic trade: `test_parity_with_engine_worth`.
- The tier checks fail on mutated copies (10 -> 11, 3 -> 2.9, >= -> >): `test_checks_fail_on_broken_module`.
- build_root_pages still passes with the module in ROOT_FILES: `tests.test_build_root_pages`.

### Claimed, not confirmed
- The team page read and its browser parity against DDF.find ship in part 2 (same ticket, next PR).
- Consumers (JEG-1559, JEG-1561) were told the signature; their use is not checked here.

### Review fixes (independent review on 2b81e4336)
- computeTeam is async now. Any error rejects its promise, so the page never stays on "Sizing" (`test_compute_team_never_hangs_on_error`).
- The trade search leaves out skipped teams and held players, as find.html does. Each move counts above its own noise floor.
- A "none" read now says why:
  - a counted gain under 3%: "too small to be worth chasing";
  - nothing beat its floor: "already sharp";
  - nothing to check;
  - too few priced players (no move named).
  Test: `test_none_reasons_are_honest`.
- Tiers and bands read the same truncated percent the page shows, so they always agree (`test_shown_and_tier_always_agree`). No −0 (`test_no_negative_zero`).
