## 2026-10-29 - JEG-1188 / JEG-1121: two bench levels from a loaded league (Claude)

Jeremy, after the real-league check (bench by value fit USO and Charlotte
worst): "My thinking is we focus on vorp, let other managers make stupid
decisions and capitalize." Then: "So we are keeping a market level of bench
and a ddf level?" ... "Yes, build it".

### What changed
- `roster_convention.league_depth(starters, order, league_rostered, level,
  league_reserve)` and the engine's `vpLeagueDepth` (value-model.js), one
  rule, per position: `bench`, `replacement`, `held`, `reserve`,
  `best_free_index`, `bench_basis`. `league_bench` / `vpLeagueBench` stay as
  bench-only wrappers.
  - `ddf` (`above_replacement`): replacement is the best available free
    agent in the projected-points order (not rostered, not in reserve); bench
    = his index minus starters, floored at 0.
  - `market` (`rostered_depth`): held = active rostered players (IR and taxi
    left out); bench = held minus starters, floored at 0.
- The waiver line reads the replacement player when a league is loaded (it
  can sit inside the starters when a free agent out-projects a starter); the
  starter counts never move. Allocation rows carry the four depth fields only
  with a league, so the no-league output is unchanged.
- `league_completeness` / `vpLeagueCompleteness`: the levels apply only when
  the team count matches the settings, no team is empty or below its starting
  spots, no player is on two teams, no pasted player is unmatched (unknown =
  unmatched), and every roster has a load time no older than 7 days.
  Otherwise the page keeps the modeled bench and says why.
- workspace.js: each team records when its roster was loaded (`rosterAt`) and
  how many pasted players are unmatched (`unresolved`), in the same store
  update as the roster (one undo step). A shared link has no load time, so it
  fails closed.
- curve-widget.js: `getLeagueLevel({rostered, reserve, level})` returns the
  level's rows, allocation, per-position counts and bench-share readout,
  cached until the page's values rebuild. `getAllRows` and
  `getAdjustmentWeights` are untouched.
- league.js: DDF Value and the bench-share weights from the ddf level; the
  four trade charts and the expected depth that judges acceptance from the
  market level. Under the team summary: which bench the numbers use, then
  three separate counts (bench seats in the settings; active players beyond
  the starters; players beyond the starters who beat the best free agent),
  then his sell candidates. A null sell block no longer renders "null".
- Compare a trade and the pair finder keep the modeled bench.
- The Natural fit rule is unchanged; its inputs on the league page are the
  level values above.

### Real leagues (each league's own settings, half PPR, 12 teams)
Bench QB/RB/WR/TE, league-wide. Bench seats are settings, not rosters.

| League | Bench seats | Rostered depth (market) | Above replacement (ddf) |
|---|---|---|---|
| USO (BN5, no IR) | 60 | 6/17/29/8 = 60 | 1/5/5/6 = 17 |
| Charlotte (BN6, IR1) | 72 | 8/27/23/7 = 65 | 4/6/8/4 = 22 |

Charlotte's 72 seats hold 65 valued players, 3 K/DEF and 4 empty spots; its
11 IR players were counted as depth before (65 + 11 = 76) and now are held,
not depth. USO's 60 seats hold 61 valued players while one QB start slot is
empty. Accounting, completeness and the pins: `tests/test_league_levels_real.py`.

Charlotte on the built page today (Daaaa Bears chosen): sell candidates
Quinshon Judkins 15.3 to him vs 20.0 at the league's depth, Omar Cooper Jr.
2.5 vs 5.6, Kaelon Black 0.0 vs 2.8.

### Verified
- `tests/test_league_bench_levels.py` (18): the rule, JS vs spec at both
  levels on the worked example, the replacement-inside-starters probe (fails
  on the old engine: a freed QB was worth 23.4 over a waiver line of 12).
- `tests/test_league_levels_real.py` (12): accounting, completeness (JS =
  Python on every case), no-league baseline against the stored pre-JEG-1188
  engine, JS = spec at none/ddf/market on both leagues, a 48-shape sweep
  (8/10/12/14 teams, 1QB/2QB/SF, 2WR/3WR, one or two FLEX) at both levels and
  a source missing half its players. Fixtures and repro:
  `tools/build_league_level_fixtures.py`.
- `tests/test_league_levels_trades.py` (new, 5): uneven trades. The league
  page's search (computePairing over findTrades) on both leagues, his team
  against every other, at the ddf level, the market level and the page
  contract. Every 2-for-1 and 1-for-2 search is evened by the right team's
  least valuable bench player; every edge and chart net is the exact sum of
  that level's rows, throw-ins included; counts pinned; on the page some
  throw-ins are worth 0.0 in DDF Value but priced by the charts. A finder that
  skips re-judging the evened trade fails it.
- `tests/test_v2_league_levels_render.py` (new, Chromium, CI only): the page
  against value_reference on both leagues at both levels (every DDF Value and
  every count), the no-league gate, rows and weights unchanged for Compare
  and the pair finder, and the rendered states (no league, complete, no team
  chosen, one team missing). Dry run here in a headless page: 0 mismatches.
- Engine, spec reference, worked example, roster convention, league units,
  v2 page build, finder and import tests: pass. `check_rank_guard`: pass, 0
  inversions. Not run here (no Chromium download): value_check compare and the
  render tests. CI runs them.

### Picks
In /mnt/project-files/ddf/picks-log.md under "JEG-1188 two-level bench".
