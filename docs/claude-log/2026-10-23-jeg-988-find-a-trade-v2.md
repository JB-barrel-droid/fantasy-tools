## 2026-10-23 - JEG-988 Find a trade v2

Contract: build the approved v2 spec (fantasy-tools-selfhost-notes/jeg-988-find-a-trade-v2/spec.md) on PR #877 as four commits,
with Jeremy's 2026-10-23 answers (natural fits first, then edge; one auto-detecting box; bench-seat depth shown as a range;
natural = both gain under their own view and fill a need) and his later additions (bench rebalancing counts as need, the
thresholds chosen by math, the thin-roster 1-for-2 case). No value, ranking, engine or `value-model.js` / `curve-widget.js`
change. No `make sync` (`make -o sync validate` was used for the gate).

### Verified (check named)

- One box per side: tests/test_v2_finder_box.py (node, 6 mutants) and test_v2_finder_box_render.py (1440, 390, 320; 5 broken builds
  caught): suggestions within 12 px under the box also with 12 players on the roster, short text is a search, a typed or pasted page
  and a one-per-line name list are read, Clear is per side with no dialog and Undo restores, kept K/DEF after Find trades.
- Score chips: test_v2_finder_chips_render.py compares every chip with the engine row computed independently (incl. a player with no
  DDF Value reading "no value", not 0); 3 broken builds caught.
- Roster balance and sentences: test_v2_finder_balance.py (node, 8 mutants) and test_v2_finder_eval_render.py (table counts and
  over/under words equal an independent computation from the engine's allocation, both views, both sides, 3 broken builds).
- Fit: test_v2_finder_fit.py (node, 9 mutants): bench rebalance with no starter gain is natural; a swap deepening an already-deep
  position is force; a starter gain that deepens depth is force; bench value is not 1:1; thin team RB1 for two RB2s (starters +2.0,
  natural when the deep team gains on its market view) and the deep team giving its star for two RB2s that fill no extra slot (force);
  they are judged on the market view; a gain inside the noise is no gain; tier order stable.
  test_v2_finder_fit_render.py: fit line on every group, tier order, group edges equal the search's (nothing added, dropped or
  re-valued), the real-data 1-for-2 package is listed and its card shows the thin team's starter value rising.
- Values unchanged: node comparison of origin/main finder.js against this branch (findTrades + groupTrades, 5 seeded 9v9 3-for-3
  fixtures, 1057 trades): identical group keys, best edges and scores in all 5; tiering is a permutation (tierOrder test).
- Regression renders, each alone under the lock: paste, collapse, arrange, finder, import, groups, impact, a11y_batch2, waterfall
  (Compare 1366x768 verdict fit).
- Pre-existing failure fixed: test_v2_finder_import's "keep flag ignored" mutant anchor was stale after PR #875.

### The fit rule (as implemented)

Per team, in its own view (you: DDF Value; they: Trade chart average):
- net = (best-lineup starter value + sum of bench value x the engine's bench share for that position) after, minus before. Bench share
  = `getBenchShareReadout()` per position (this league: QB 0.235, RB 0.098, WR 0.119, TE 0.044, overall 0.117).
- noise floor tau = max(0.05, 1 x sqrt(sum of squared standard errors of the players moving)); a player's standard error is half the
  gap between his chart-based and projection-based DDF Value, or the standard error of the mean of the available charts.
- up = net > tau, down = net < -tau, otherwise level.
- need = distance outside the expected depth band (starters + bench seats per team from the engine's allocation, rostered/teams, shown
  as lo-hi; counted players need a usable value of 0.05 or more in that view) summed over QB/RB/WR/TE, plus empty starting slots.
  toward = need falls, away = need rises. A roster below the starting-slot count is not judged on depth.
- served = (up and not away) or (level and toward). Natural = both served and at least one toward; value = both served, none toward;
  force = otherwise (a team loses, gains nothing measurable, or gains while deepening a deep position / thinning a thin one).
- Groups are ordered natural, value, force; inside a tier the existing edge ranking. The card shows the label and both nets.

Threshold evidence (Yahoo vs ESPN fixture rosters, 3-for-3, 167 trades in 19 groups; engine data 2026-10-23): per-player standard error
median 1.8 (DDF) and 2.3 (charts), 90th percentile 4.8 and 6.5; tau for these groups median 7.3 (DDF) and 8.1 (market), 90th pct 8.9
and 10.2; |net| median 6.5. Labels (natural/value/force): z=0.5: 4/1/14, z=1: 3/0/16, z=2: 0/0/19. Groups that change label: 2 at
half and 3 at double (of 19). Top-30 9v9 rosters (108 groups): 0/0/108 at z=1 and z=2, 0/1/107 at z=0.5; 1 flip at half, 0 at double.
Natural fits are rare by construction: the search keeps trades the charts call even for them, so a market gain beyond noise is rare.

### Claimed, not confirmed

- Typed search cannot add a defense or kicker (the engine has none); see GAP-FINDER-NO-KDEF-ROWS.
- The roster-page fixtures are the only real-data rosters used; the 1-for-2 case uses names chosen from the engine at run time.
- The bench share is the engine's per-position share of starts, taken as the weight of a bench unit; not independently validated.
- Expected depth moves with PR #867 (bench share engine) when it merges; the code reads the engine's allocation, so it follows.
