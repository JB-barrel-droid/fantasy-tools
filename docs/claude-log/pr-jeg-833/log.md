## 2026-10-22 - JEG-833 Trade targets Buy compares at the charts' rank

- Problem (round-2 review): after JEG-820 the Buy list was still the overall
  top five (Smith-Njigba 64.7 vs 38.7, Gibbs 69.6 vs 50.9, Nacua, Walker,
  Bijan) because our top end is steeper than the charts'. Phone QA added: the
  lists were not in the "biggest gap first" order their copy claimed, and the
  market cell showed the same difference with the opposite sign.
- Measured (2026-10-22 build, USA Today + FantasyCalc + FantasyPros compared,
  headless `window.TradeValueV2.targets()` on the 12 setups): the ticket's A
  (position-share gap) keeps the top tier (Full PPR 12 share gap: Smith-Njigba
  -35%, Nacua -33%, Chase -31%, Walker -27%, Gibbs -21%); B (consensus < 35)
  moves the same effect down the board (St. Brown, McCaffrey, Lamb, Allen);
  C (percentage) puts Kirk +159% at 0.0 and Allen +105% first; a per-position
  median-ratio residual still has the top five at +34% to +60%. The
  rank-equivalent gap (our value at the charts' position rank minus our value)
  is 0.0 for the top five at every setting and lists, Full PPR 12: McCaffrey
  (charts RB8, we RB5, -6.4), Hubbard (RB12 vs RB10, -5.0), Breece Hall (RB18
  vs RB17, -4.1), Jefferson (WR9 vs WR6, -2.9), Judkins (-4.4), Goff (-3.4),
  Mahomes (-3.5), Davante Adams (-3.3). Standard 10: McCaffrey, Jefferson,
  Jacobs, Judkins, Goff, Pollard. Half PPR 8: McCaffrey, Hubbard, Jefferson,
  Jacobs, Goff. The ticket's regression guard (a monotone steeper rescale gives
  no Buy) holds exactly under this rule and fails under A.
- Fix: `rankEquivalents` in `app/v2/targets.js` (per position over every
  compared player; `buildTargets` takes all rows and a `keep` filter so a name
  search cannot move a rank); Buy = rankGap <= -2 (`BUY_RANK_MARGIN`) by
  |rankGap| x min(ours, consensus); the rest counted as `scaleOnly` with a
  footnote naming the top five by ours. v2.js: Buy column "Gap at chart rank", `.t-score` sub-line on every row and card (table: inline rounded "score 32" with the ranks in the tooltip, `data-score`
  keeps one decimal; card: "RB8→RB5 · score 32.1"; Sell "score 49"), meta "ranked by gap × value at stake,
  biggest score first", market cell "▼ 3.3 below" instead of "▼ −3.3".
- Verified: `tests.test_v2_targets` green with 9 new mutations (Buy by
  consensus gap, margin dropped / moved, sign flipped, ranks on the searched
  subset, ranks across positions, scale-only not counted, max for min, floor
  on Buy) each caught; the same checks against main's targets.js give 17
  errors. `tests.test_v2_targets_render`: see the PR (order follows the shown
  score, scores non-increasing, copy says the rule, Buy rows name both ranks).
- Not run: the 12-combo sweep (engine untouched). Not a value-math change: no
  Python reference.
