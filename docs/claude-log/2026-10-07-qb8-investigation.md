## 2026-10-07 - GAP-QB8-FEASIBLE investigation (investigate/qb8)

Contract: find out why `make validate` fails tests.test_two_tier_frontend at
8 teams ("QB: no feasible bench share <= 0.15") on the fresh 2026-10-07 ESPN
anchor, decide whether it is the data or the code, and bring options.
Investigation only; nothing here changes engine math on main.

### Answer in one line
It is a bug in the test harness, not in the data or the method. At 8 teams
QB calibrates cleanly at the default 0.15 on the fresh data (feasible window
0.086..0.258). The harness's `maxfeasible` re-implements the fallback as a
plain bisection on [0.01, 0.15] that never tries 0.15 itself; its first
midpoint is 0.08, and the fresh QB window's lower edge (0.086) now sits
above 0.08, so the bisection walks out of the window and returns null.
Production code (browser `calibratePositionFeasible`, leg builder
`build_leg`, Python test helper `feasible_share_for`) all try the requested
share first and use 0.15 for QB at 8 teams.

### What the bound is
- Per position, `solveTierPrices` (curve-widget.js TwoTier; mirror
  `solve_tier_prices` in pipelines/build_ddf_two_tier_leg.py) solves a 2x2
  system for a bench rate pb and a starter rate ps so that bench players get
  `share * pie` and starters `(1 - share) * pie`. It is feasible iff
  pb > 0 and ps > pb (a starter slice pays more than a bench slice).
- Feasibility is independent of the pie (pb, ps are linear in it). The
  feasible set is an interval [lo, hi]: hi is the "natural" share (bench
  surplus / total surplus, where pb = ps); below lo the bench rate goes
  non-positive.
- Fresh data: the QB pool between QB2 and QB15 flattened, so bench QBs sit
  closer to the starters and need a larger slice before pb stays positive:
  QB 8-team lo moved 0.059 -> 0.086, hi 0.212 -> 0.258 (frontend pool).
  0.15 stays well inside. Genuine data movement, nowhere near infeasible.

### Verified (check named)
- Fresh ESPN pull: `pull_espn_projections.py --out <scratch> --force`, 496
  rows, vintage 2026-10-07 (Lamar ROS 280.25 -> 256.68).
- players.json espn_ppg reconstructed from the CSV (eligible rows, half +-
  0.5*rec, / games_remaining from Supabase games). On the committed
  2026-10-03 CSV this reproduces committed players.json exactly except 4
  alias spellings and one fringe WR. Patched into a worktree players.json:
  `python3 -m unittest tests.test_two_tier_frontend` gives the same 6
  failures the players-bake simulation saw (3 x all_configs, 3 x
  slider_change, all `*/8`, QB). Same module OK on committed data.
- Direct harness probe on the fresh QB 8-team tier: `calibrate` at 0.15 is
  valid (ppr pb 2.00, ps 11.84); `calibrate` at 0.08 fails "bench rate
  -0.18 not positive"; `maxfeasible` returns null. Production
  `TwoTier.calibratePositionFeasible(tier, pie, 0.15)` returns 0.15.
- Leg builder on the fresh CSV (ROS/16 pool, pie = surplus): QB window
  0.073..0.247 at 8 teams; 0.15 used directly. 12-team ppr QB1 (Allen) 29.5,
  which matches the players-bake simulation's ESPN full_12 value.
- Prototype fix (option A, on this branch): harness `maxfeasible` calls
  `T.calibratePositionFeasible` instead of its own bisection.
  tests.test_two_tier_frontend: OK on the fresh patched players.json and OK
  on committed players.json. `make test-core` (committed data, no build):
  every module OK except tests.test_published_surfaces, which needs the
  built dist/ (consolidated-values.json absent in this unbuilt worktree;
  unrelated to the harness).
- Guard still catches the broken states (synthetic QB tiers, exposures
  scaled): window entirely above 0.15 [0.151, 0.213] -> share null (caught);
  no feasible share at all -> null (caught); window containing 0.15
  [0.121, 0.151] -> 0.15 (old harness: null, the false alarm).

### Page at 8 teams with fresh data (Q2)
Leg-builder values (the ESPN DDF leg the ESPN section is built from), QB,
8 teams, PPR. All finite, none negative, 15 QBs above the waiver line (same
as 10-03), waiver QB16 = 0. Options A/B/C publish exactly this column.
Columns D/0.20 show what forcing a different QB share would do.

| # | QB | ppg 10-03 | ppg 10-07 | value 10-03 | value 10-07 at 0.15 (A/B/C) | QB share 0.10 (D) | QB share 0.20 |
|---|---|---|---|---|---|---|---|
| 1 | Josh Allen | 19.65 | 19.28 | 33.2 | 27.2 | 31.9 | 22.4 |
| 2 | Brock Purdy | 17.32 | 17.50 | 12.7 | 13.0 | 14.2 | 11.8 |
| 3 | Jayden Daniels | 15.50 | 17.29 | 1.8 | 11.3 | 12.1 | 10.5 |
| 4 | Trevor Lawrence | 16.85 | 16.91 | 8.8 | 8.5 | 8.6 | 8.4 |
| 5 | Joe Burrow | 16.44 | 16.84 | 6.0 | 7.9 | 7.9 | 7.9 |
| 6 | Tyler Shough | 16.34 | 16.46 | 5.4 | 5.3 | 4.8 | 5.9 |
| 7 | Patrick Mahomes | 16.32 | 16.29 | 5.2 | 4.3 | 3.6 | 5.1 |
| 8 | Drake Maye | 15.82 | 16.22 | 2.9 | 3.9 | 3.2 | 4.7 |
| 9 | Bryce Young | 14.99 | 16.09 | 0.3 | 3.3 | 2.5 | 4.1 |
| 10 | Lamar Jackson | 17.52 | 16.04 | 14.3 | 3.1 | 2.3 | 3.9 |
| 11 | Jalen Hurts | 16.81 | 15.94 | 8.5 | 2.7 | 1.8 | 3.5 |
| 12 | Dak Prescott | 16.42 | 15.84 | 5.8 | 2.3 | 1.5 | 3.1 |
| 13 | Jared Goff | 15.36 | 15.52 | 1.4 | 1.3 | 0.7 | 2.0 |
| 14 | Matthew Stafford | 15.72 | 15.36 | 2.5 | 1.0 | 0.5 | 1.5 |
| 15 | Deshaun Watson | 13.81 | 15.24 | 0.0 | 0.7 | 0.3 | 1.1 |
| 16 | Kyler Murray | 15.71 | 14.89 | 2.5 | 0.0 | 0.0 | 0.0 |
| 17 | Bo Nix | 14.77 | 14.69 | 0.0 | 0.0 | 0.0 | 0.0 |
| 18 | Jordan Love | 14.87 | 14.63 | 0.0 | 0.0 | 0.0 | 0.0 |
| 19 | Sam Darnold | 14.76 | 14.50 | 0.0 | 0.0 | 0.0 | 0.0 |
| 20 | Jacoby Brissett | 13.58 | 14.29 | 0.0 | 0.0 | 0.0 | 0.0 |

Other scorings, 8 teams: QB1 standard 34.4 -> 36.6, half 35.7 -> 34.8;
QB8 5.6 -> 5.3 / 5.8 -> 5.0. The big individual moves (Lamar 14.3 -> 3.1,
Hurts 8.5 -> 2.7, Daniels 1.8 -> 11.3) are ESPN's own projection changes,
not the method. Other team sizes (ppr, 10-03 -> 10-07): QB1 10t 23.5 ->
22.3, 12t 26.7 -> 29.5, 14t 24.9 -> 31.9. No negative/NaN values in any of
the 12 combos. The rendered page was not opened (no full chain rebuild here).

### Near the boundary (Q3), fresh data, frontend pool, all 48 cells
- 0.15 above the window top (downward fallback used, works): RB
  standard/12 -> 0.146, RB half/8 -> 0.149. On 10-03 it was 7 TE cells and
  RB ppr/8; those are all inside now.
- Lower edge near the old bisection trap (0.08): QB/8 0.086 (trips it), QB/14
  0.077 (0.003 from tripping it). QB is scoring-independent, so all three
  scorings move together.
- No cell has its window above 0.15. No cell is infeasible.
- Roster shape does not enter: the calibration pool uses the fixed reference
  shape (REF_SLOTS), per scoring x teams.
- Slider: the range is fixed at [0.01, 0.30]. At 8 teams, a QB share below
  0.086 now withholds QB in the browser (pb <= 0 has no upward fallback in
  `calibratePositionFeasible`; the leg builder does scan upward, JEG-74).
  Was below 0.059 on 10-03. User-driven, fails closed, not a gate issue.

### Latent production bug (same shape, not triggered today)
`calibratePositionFeasible` (JS) and the `economics break` branch of
`build_leg` (Python) use the same bisection on [0.01, requested] when the
requested share is infeasible from the top. If a position's window is
[lo, hi] with hi < 0.15 and lo above the first midpoint (0.08), both
withhold a position that has feasible shares (synthetic tier window
[0.086, 0.092] -> null). No real cell is there today (RB lo ~0.03).

### Options
- A. Fix the harness (recommended). `maxfeasible` calls production
  `calibratePositionFeasible`; the test then checks the code the page runs.
  Numbers: none move (QB uses 0.15 in production already). Risk: none to
  values; the guard still fails on window-above-0.15 and no-window states.
  Patch on this branch (tests/two_tier_harness.js). Also removes a silent
  `T.DEFAULT_BENCH_SHARE_TT` (undefined on T) default.
- B. A plus harden the fallback bisection in JS and Python: when the
  plain bisection finds nothing, scan down from the request in 0.005 steps
  for a feasible anchor, then bisect. Run it only as a second pass so every
  share the current code finds stays bit-identical (a first-pass rewrite
  moved fallback shares ~1e-7, which breaks the 1e-9 JS/Python parity
  vectors). Numbers today: none. Risk: low; two files in lockstep; needs a
  test that fails on the synthetic trap tier. Optionally port JEG-74's
  upward scan to the browser so the slider never withholds a position
  the leg builder prices (that is what closed PR #397's
  calibratePositionNearest did for CBS ROS / Razzball).
- C. Make the check a warning. Numbers: none move (same as A). Risk: hides
  a real future failure (window above 0.15, or none) behind a warning on
  the deploy gate's two-tier module; strictly worse than A.
- D. Lower the QB share floor / change the QB bench count at small
  leagues (what the GAP row proposed). Not needed: 0.15 is feasible.
  Forcing QB to 0.10 at 8 teams moves Allen 27.2 -> 31.9 and QB9-15 down
  20-60% (table). Methodology change for Jeremy; no reason to make it to
  unblock the bake.

Recommendation: A now (unblocks the daily anchor refresh; zero value
movement), B as a follow-up hardening ticket.

### Separate finding (not this gap)
Supabase public.games 2026 has only weeks 1-2 marked final (31 final, 241
scheduled; MCP execute_sql), so bake_players' games_remaining is 15 for most
teams (16 for LA, NYG) while ESPN ROS covers weeks 5-18. players.json
espn_ppg (the browser's live pool) is ROS / 15 or 16 instead of the true
remaining games, and the per-team divisor differs for the wrong reason.
Not verified against the true schedule. The leg builder uses ROS / 16 for
everyone, so the baked ESPN leg is unaffected. Logged as
GAP-GAMES-REMAINING-STALE.

### Claimed, not confirmed
- Full chain rebuild + `make validate` with option A on fresh data was not
  run (players.json reconstructed, not baked: the bake needs a players
  registry dump; anon cannot read public.players).
- The rendered page at 8 teams was not opened.
