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

## JEG-1249 corrections (Codex review of 54279710), 2026-10-29

1. **Replacement identity.** The ddf level's replacement is a player
   (`replacement_key`, the best free agent in the common order). Each source
   prices its waiver at his own value there; a source without him uses its
   own best free player; no free row is insufficient_coverage. JS, spec
   reference and value_reference (`roster_convention.replacement_waiver_index`).
   Codex's Q11 probe: waivers 40/18, Q11 worth 0.
2. **Market depth.** Market starters come from held players only
   (`roster_convention.market_order`); rostered = held, bench = held -
   starters, theoretical demand kept as `modeled_starters`. Complete-capacity
   SF/FLEX probe: rostered 80/100/120/140, bench 16/20/24/28 in all three
   implementations.
3. **Provenance.** JEG-1241's helper (#1108 at dc10602d, merged into this
   branch) is wired into workspace.js and league.js. Teams keep a
   `provenance` record; pastes, appends, "Yes, add", Search to add, removals,
   clears and share links each go through its transitions. The league check
   adds `inferenceBlockers`; every reason blocks except `coverage_unproven`.
   Jeremy, 2026-10-29: "This hasn't been an issue on prior pastes. The
   rosters have all filled up and the page is set up for manual checks and
   errors." A paste is read as the team's whole roster, and the levels note
   says so; a page that left the bench out still blocks.
4. **Compare handoff.** While the league's rosters set the bench, the league
   page holds its "Open in Compare a trade" link and says why. With the
   standard bench on both pages the link opens the same trade at the same
   values. Carrying rosters and gains into Compare stays with JEG-1229.
5. **Integrated proof.** `tests/test_jeg1249_league_site_render.py`
   (Chromium): the provenance gate on the page, the paste transitions through
   the team box, and the league to Compare journey (an equal trade, a
   throw-in trade, its core as a true unequal package, an unpriced player and
   a kicker, the saved league unchanged, the hold with league pricing).
   JEG-1240's contract (`tests/node/uso_site_journey_contract.cjs` from #1110)
   passes 9/9 on this branch's app/v2.

Finding, not a change here: on the real USO rosters (this fixture, his team
marked) the league table shows 101 trades and none sends JSN, on main
b8630697 and on this branch alike.

## JEG-1249 review fixes (independent Claude review of 3418629f, fb70682d), 2026-10-29

Contract: fixes 1 and 2 of the review. Back out the generated churn from 9de97320, then merge main normally. Fix 3 (carry the band onto #1077's merged head) waits until #1077 merges.

### Verified (check named)
- eda34793: the 21 generated paths 9de97320 touched match origin/main (`git diff --cached origin/main -- <paths>` empty, at bfc30cca and again after merging 434bfd76).
  - The paths: three app/trade-value-chart JSON assets, the app index.html and every dist/ path.
  - Four of them are not on main and are removed: dist/ddf-skill.zip, dist/connect/index.html, dist/get-values.openapi.yaml, dist/value-logic/index.html.
  - A sync run regenerates exactly these four as untracked files (seen in `git status` after the test run).
  - No other branch commit touches the 21 paths (`git log origin/main..branch --no-merges -- <path>`).
- a91b480d merges main 434bfd76.
  - league.js: kept #1138's Buy/Sell copy and #1105's sellBlock. Against base 430791c4, main changed only those two copy lines and #1105 only the replaceChildren line. The other #1138 league.js hunks are present (grep). `node --check` passes.
  - HANDOFF.md: kept #1105's JEG-1249 block and updated it.
- 135 passed, 133 subtests, at a91b480d, with Google Chrome via CHROMIUM_PATH and RENDER_TESTS_REQUIRED=1.
  - Unit modules: test_jeg1249_bench_corrections, test_league_bench_levels, test_jeg1130_copy_glossary, test_v2_copy_names, test_rank_guard, test_roster_provenance_transitions, test_spec_reference, test_spec_reference_value_pipeline, test_value_reference_worked_example.
  - Render modules: test_v2_league_levels_render, test_jeg1249_league_site_render, test_v2_league_tables_render, test_v2_contract_render.
  - The test build rewrote generated files in the working tree; they were discarded and none were committed.

### Claimed, not confirmed
- Value math is unchanged by fixes 1 and 2: only generated files, the merge and docs moved. The before/after DDF Value table is regenerated after fix 3, on the final head.
- The full suite and make validate were not run locally; preview CI runs them.

## JEG-1249 fix 3: main (#1077) merged, band carried to the line row W, 2026-10-30

Contract: the 2026-10-30 02:49 UTC "To Mac:" comment on JEG-1249. Merge origin/main (which now holds #1077's squash 2458aeb7) into 3ff07d54 normally, carry the seven-player band resolution from `claude/JEG-1249-band-integration` d07f6527 (read, not merged), and regenerate the USO before/after table.

### Verified (check named)
- 1162a6f2 merges origin/main e18d640a (2458aeb7 plus #1186 and a JEG-205 hash commit). No rebase, no force push.
- Conflicts, one line each:
  - value-model.js: #1105's league-depth helpers then #1077's `vpWaiverBand`; the line is `family === "projection" ? vpWaiverBand(work, W) : work[W].native`. Byte-identical to d07f6527 (`git diff d07f6527 -- <file>` empty).
  - spec_reference/value_pipeline.py: `_convention_waiver_band_line(..., W)` for projections, `work_val[work[W]]` for charts. Byte-identical to d07f6527.
  - value_reference.py: `_waiver_value(src, p, ..., n_line)`. Byte-identical to d07f6527.
  - v2.css: both rules kept (JEG-1236 text box height, JEG-1249 levels switch).
  - build_v2_page.py: main's copy list (player-status.js, trade-context.js, player-flags.js) plus #1105's roster-provenance-transitions.js.
  - HANDOFF.md: both blocks kept.
- d07f6527's own test and fixture resolution was applied on top (`git diff <auto-merge tree> d07f6527 -- tests/`): test_jeg1249_bench_corrections, test_league_bench_levels, test_league_levels_real, test_league_levels_trades, test_waiver_band_line and the USO/Charlotte fixtures. Each is byte-identical to d07f6527.
- Generated paths equal main: `git diff origin/main --stat -- app/trade-value-chart/assets/{comparison-sources-data,lineup-parameters,reference-freshness}.json app/trade-value-chart/index.html dist/` is empty at 1162a6f2.
- Focused, 115 tests: test_jeg1249_bench_corrections, test_league_bench_levels, test_league_levels_real, test_league_levels_trades, test_waiver_band_line, test_spec_reference_value_pipeline, test_value_reference_worked_example (3189 numbers, 0 mismatches), test_roster_provenance_transitions OK; test_rank_guard 26 OK (with CHROMIUM_PATH).
- Render with RENDER_TESTS_REQUIRED=1 and Google Chrome: test_v2_league_levels_render 2, test_jeg1249_league_site_render 4, test_v2_league_parsed_render 2, test_v2_league_tables_render 2, test_v2_contract_render 6, all OK.
- Fails before, passes after: the band anchored at N (`vpWaiverBand(work, N)`) gives 226 failures in test_jeg1249_bench_corrections + test_league_bench_levels + test_league_levels_real (40 tests), and TestLoadedLeagueBandParity fails; restored to W, 40 OK and parity OK.
- USO before/after DDF Value, JS engine on the frozen fixture (standard bench / DDF level / market level): JSN 69.4/71.4/72.9, K. Williams 55.9/58.8/51.9, Josh Allen 33.9/40.7/36.2, Aaron Jones 9.7/5.4/8.0, Goedert 2.6/5.3/4.0, Hockenson 2.3/4.6/3.5. At the DDF level 85 of 741 players move more than 1 point (104 at the market level). Identical to the d07f6527 preview, as expected: #1077 changed nothing in the three engine files after 217958ce.
- `make validate` (system python3, CHROMIUM_PATH=Google Chrome): reference, sync, guard-harness, test-integration (8 modules) and value-check-compare pass. value-check: verdict agree, 1,205,082 values, 0 mismatches. `pipelines/check_rank_guard.py`: 12 chart x combo checks, 0 inversions.
  - test-core stops at `tests.test_v2_finder_saved_team_render` test_keyboard_mobile_and_overlap_guard (`'' != 'beta'`). The same test fails the same way on a clean origin/main e18d640a worktree, so it is a local baseline red, not this merge (known local-only, green in CI). Every test-core line after it was run one by one: 70 commands, all exit 0.
- Test runs rewrote generated app/dist files in the working tree; they were discarded and none were committed.

### Claimed, not confirmed
- CI on the pushed head (preview-build, shards, v2-render) had not reported when this entry was written.

## JEG-1249 merge gate: main merged, phone card and copy list, 2026-10-30

Contract: the 12:52 UTC merge-gate comment on JEG-1249 (Jeremy's "A" on the USO table, 13:02 UTC).

### Verified (check named)
- dc5d6c89 merges origin/main 301c8678 (contains 66c9329f) normally.
  - league.js phone opponent card: main's six `data-line` rows (trade, capture, proj, ours, market, theirs), with main's raw `#compare-trade` anchor replaced by `compareLink(r, ctx)`. `node --check` passes.
  - build_v2_page.py copy list: `trade-readout.js` and `roster-provenance-transitions.js` both present.
  - HANDOFF.md: both blocks kept.
- Byte-identical to d07f6527 (`git diff --stat d07f6527 -- <paths>` empty): value-model.js, roster-convention.js, roster_convention.py, both references, the league fixtures and the six league/band test modules. The approved USO table therefore holds.
- Generated app/dist paths equal origin/main (`git diff origin/main --stat` empty).
- Units, 140 tests: the nine focused league/band/reference modules, test_rank_guard, test_jeg1213_logic, test_jeg1213_summary_fields and test_uso_site_journey_contract. The only failures are test_uso_site_journey_contract's two continuity checks (`basis-changed` on another device). They fail identically on a clean origin/main 858bdc32 worktree and are red by design until context carries across devices (JEG-1240 notes).
- Render with RENDER_TESTS_REQUIRED=1 and Google Chrome:
  - OK: test_v2_league_levels_render 2, test_jeg1249_league_site_render 4, test_v2_league_parsed_render 2, test_v2_league_tables_render 2 (includes the JEG-1232 phone-card line checks), test_jeg1213_acceptance_render 11 and test_v2_contract_render 6.
  - test_uso_site_journey_render: test_journey_keeps_the_trade_context and test_unequal_deal_keeps_its_package fail identically on clean origin/main (baseline red).
  - test_guard_fails_on_a_link_without_get failed only on this branch ("mutation anchor is stale", 1 != 2). Its assertion counted two copies of the raw anchor; #1105's compareLink leaves one. 5833d24e changes the count to 1 (an assertion pinning code shape, not the rule); the guard then passes, catching the mutant as package-changed only.

### Claimed, not confirmed
- The USO journey suites are not in the Makefile or any workflow, so CI does not run them.
- Full CI on the pushed head had not reported when this entry was written.

## JEG-1249: Node harness copy lists, 2026-10-30

Contract: the 14:50 UTC "To Mac:" comment on JEG-1249 (render-tests red at e0b2319e).

### Verified (check named)
- `#1105`'s app/v2/workspace.js requires ./roster-provenance-transitions.js. Two of main's tests copy page modules into a temp folder without it, so their Node harness crashed with "Cannot find module './roster-provenance-transitions.js'". Harness fixes only, no assertion changed.
  - tests/test_jeg1231_opponent_inclusion.py MODULES (the comment's fix): 7 failures before, 2/2 OK after.
  - tests/test_jeg1328_share_links.py FILES (same cause, found by checking every test that loads workspace.js): 9 errors before (the harness printed no JSON), 2/2 OK after. It passes on clean origin/main f2d50519.
- The other workspace.js harnesses: test_jeg1320_discovery_controls and test_v2_league_units OK. test_jeg1229_trade_context (1 failure) and test_uso_site_journey_contract (2 continuity failures) fail the same way on clean origin/main f2d50519, so they are baseline.
- No engine, reference or fixture file changed; they stay byte-identical to d07f6527.
