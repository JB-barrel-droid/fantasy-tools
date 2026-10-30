## 2026-10-29 - JEG-1324 Natural fit 1a predicate (both sides' projections)

Contract: put Jeremy's Natural fit 1a ("1a", 2026-10-29; "Natural means both sides, not just 1 side") in one shared
predicate. Both teams pass their value test and their own roster construction, and neither team's DDF Value
(projections) falls. Point the finder's Natural label and the league table's `ourFitOf` at it. Slice 5 of
`docs/specs/trade-page-parity.md`.

What changed:
- `app/v2/finder.js`: `naturalFit(parts)`, `projectionsHold(net)`, `PROJ_FLOOR` (= the 0.05 display floor, D2 pick A)
  and `viewNet`. `tradeFit` now labels Natural only when `naturalFit(...).ok`, and returns `natural` ({ok, us, them}).
  `fitText` names the side whose projections fall, or says they were not checked. The Natural tooltip gains one clause.
  The predicate stays in finder.js because the connector (supabase/functions/mcp/fit.ts) evaluates only this file, so it
  follows the rule with no edge change. That still takes the site deploy, then the connector's 5-minute cache.
- `app/v2/opportunities.js`: `ourFitOf` reads `fit.natural.us` and never says "natural". The labels are JEG-1221's S5
  strings: works / gains, roster issue / gains, projections fall / gains, projections not checked / doesn't work.
- Jeremy decided both picks on 2026-10-29 ("A" and "A"; `docs/decisions.md`): a fall under 0.05 holds, and if a moving
  player has no DDF Value (projections) the test is not judged and the trade is not Natural. The measure is the
  bench-weighted net, the same as the other Natural tests (Claude pick, in the picks log).

### Verified (check named)
- `python3 -m unittest tests.test_v2_finder_fit tests.test_v2_finder_trifit tests.test_v2_league_units
  tests.test_v2_finder_balance`: OK. New checks: 16 (the predicate at ±0.049, ±0.05, ±0.051, 0 and null), 17 (the same
  boundaries through tradeFit on both sides), 18 (a held projection), 19 (the 14:24 shape: only their projections fall
  2.2). Six new finder mutants and two new opportunities mutants are each caught.
- Fails without the change: `check()` from tests/test_v2_finder_fit.py raises on main's finder.js (no `projectionsHold`),
  and checks 18 and 19 label Natural there.
- `node tests/node/fit_diagnostic.cjs --assert` (20-team fixture, synthetic projections added to its rows): Natural 1925
  -> 200, Market 2698 -> 4312, Force 1070 -> 1181 of 5693 (before = the same script on main's app/v2).
- USO league (12 rosters read through the Flaim connector 2026-10-29, Tiny Hands = you, K/DEF left out). Values come from
  the get-values handler run locally on the dist/ this session built (as_of 2026-10-29, USO roster shape, half PPR).
  Rows: 1129. Natural 217 -> 38, Market 617 -> 708, Force 295 -> 383. 179 flipped (91 to Market, 88 to Force), none
  newly Natural. Your projections fall in 81 of them, theirs in 102, both in 4. 104 fall by 2 or more, 7 by 0.05 to 0.1.
- 14:24 example 1 flips. Imitative deception, Deebo + A. Williams for J. Coleman + Sutton was Natural on main and is
  Market supported now: their DDF Value (projections) falls 2.3 (2.2 at 14:24). Example 2, JSN + A. Williams for
  Walker + E. Wilson, is Market supported on main and here (construction issue on today's rosters). It now also says
  your projections fall 3.1 (3.2 at 14:24).
- `node tests/league_harness.cjs app/v2 tests/fixtures/league`: 53 checks, no failures.
- `make validate` locally: sync, reference and guard-harness passed, and every test-core module passed except one.
  `tests.test_week_history` errors in one test because this container has no `playwright` Python module, and make
  stops there. The 25 test-core modules after it were run one by one: all OK. The generated dist/ churn from the sync
  was not committed.

- CI `v2-render` on acf49664 failed `tests.test_jeg1213_acceptance_render.test_opportunity_order_projection_position_and_fit_explanations`
  ("fixture has no natural info control"). Reproduced in node with the get-values handler on the dist built from acf49664
  (12 teams, PPR, QB1 RB2 WR2 TE1 FLEX1): the frozen 4-team league has 20 Natural rows on main and 0 here (58 Market,
  41 Force). Every former Natural row has one team's DDF Value (projections) falling, often the mirror of the other's gain.
  The test now requires the Market control as before, checks a Natural control only when the league has one, and reads the
  Natural definition from `fitTip("natural")` (roster, starter, projections). The assertion changed because Jeremy's 1a
  changed what Natural means, not to go green.

### Claimed, not confirmed
- The fixed acceptance test was not run here (no Chromium); CI runs it.
- `tests.test_v2_finder_eval_render` (daily render sweep, not PR CI) expects Natural groups for ESPN mine / Yahoo theirs on
  current data. Not checked; the rule may leave that pair with none.
- `value-check-compare` and `test-integration` need Playwright and did not run here; CI runs them. No engine or value
  file changed (finder.js and opportunities.js only), so `value_check compare` and the rank guard should stay
  unchanged.
- No browser QA (no Chromium in cloud sessions). League table and finder rendering of the new our-fit labels and fit
  text is inferred from source.
- `tests.test_mcp_remote.test_connector_fit_label` fails on main before this change ("the diagnostic's rows are the same
  trades"). It is pre-existing and not fixed here; the Natural count part of that check now passes.
- The connector picks up the rule only after the site deploy; not checked live.
