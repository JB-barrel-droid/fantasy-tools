## 2026-10-29 - JEG-1188 / JEG-1121: two bench levels from a loaded league (Claude)

Jeremy, after the real-league check (bench by value fit USO and Charlotte
worst): "My thinking is we focus on vorp, let other managers make stupid
decisions and capitalize." Then: "So we are keeping a market level of bench
and a ddf level?" ... "Yes, build it".

### What changed
- `roster_convention.league_bench(starters, order, league_rostered, level)`
  and the engine's `vpLeagueBench` (value-model.js): bench seats per position
  from the league's own rosters.
  - `ddf`: index of the best available free agent in the projected-points
    order minus starters (he is the replacement).
  - `market`: rostered players at the position minus starters.
- `setting.league_rostered` / `setting.bench_level` in the JS engine, the
  spec reference (`Setting`) and the Python reference (`League`,
  `Setting(..., league_rostered=, bench_level=)`). Absent = today's rule.
- curve-widget.js: `getLeagueRows({rostered, level})` and
  `getLeagueAllocation(...)` run the current week once more with those
  fields (same sources, included set, pie, overrides; no prior week), cached
  until the page's values rebuild.
- league.js: with every team loaded (team count equals the settings' team
  count, every team has players), DDF Value comes from the ddf level and the
  four trade charts from the market level. A note under the team summary
  headline says so, and lists his sell candidates (market-level DDF Value
  beats the ddf level by 2.0 or more).
- The Natural fit rule and the values it reads are unchanged.

### Verified
- `tests/test_league_bench_levels.py` (new, 10 tests): the rule alone; JS vs
  spec reference at both levels on the worked example, every leaf; bench
  counts per level (fails on main: the engine ignores `league_rostered`);
  the Python reference's League. Pass.
- `tests.test_value_pipeline_engine`, `test_spec_reference_value_pipeline`,
  `test_value_reference_worked_example`, `test_roster_convention`,
  `test_roster_convention_parity`, `test_v2_league_units`,
  `test_build_v2_page`: pass. Worked example 0 mismatches.
- No league: spec reference pipeline output over all 13 settings is
  byte-identical to main (paths and timestamps aside).
- `pipelines/check_rank_guard.py`: pass, 0 inversions.
- Not run here (Playwright browsers can't be downloaded in this sandbox):
  `pipelines/value_check.py compare` and the rendered tests
  (`test_python_reference_flag_on_equals_baseline`,
  `test_public_copy_no_vorp` rendered cases). CI runs them.

### Real leagues (each league's own settings, half PPR, 12 teams)
Bench seats QB/RB/WR/TE, league-wide:

| League | No league (today) | DDF level | Market level |
|---|---|---|---|
| USO (QB1 RB2 WR3 TE1 FLEX1 BN5) | 4/27/24/5 | 1/5/5/6 | 6/17/29/8 |
| Charlotte (QB1 RB2 WR2 TE1 FLEX1 BN6, IR counted) | 8/29/30/5 | 4/6/8/4 | 9/30/29/8 |

Best free agents (projected points per game): USO QB Patrick Mahomes 17.9,
RB Alvin Kamara 7.2, WR Alec Pierce 7.8, TE Mike Gesicki 6.7; Charlotte QB
Malik Willis 16.9, RB Jadarian Price 7.7, WR Caleb Douglas 8.1, TE Pat
Freiermuth 6.9.

League-wide Find a trade on the built page (jsdom, fixture date 2026-10-26):
USO 70 -> 60 (natural 32 -> 26), Charlotte 74 -> 178 (natural 44 -> 108).
The 20-team reference fixture is unchanged (the engine prices 12 teams, so
the levels don't apply).

Sell candidates on the built page: USO (Tiny Hands) Rome Odunze 5.0 to him,
9.3 at the league's depth; Aaron Jones 11.2 vs 14.8; Keenan Allen 0.0 vs
3.4. Charlotte (Daaaa Bears) Quinshon Judkins 11.8 vs 17.0; Emanuel Wilson
0.0 vs 3.2.

### Picks
In /mnt/project-files/ddf/picks-log.md under "JEG-1188 two-level bench".
