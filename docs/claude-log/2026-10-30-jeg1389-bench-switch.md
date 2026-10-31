## 2026-10-30 - JEG-1389 (correction to #1105, child of JEG-1249): standard bench on live, and the league rosters switch

Contract: the JEG-1389 findings on the live site at 760a1cb9 (USO league, checked 2026-10-30 18:29 UTC). (1) With league
rosters off, the standard bench did not match the approved table: JSN 67.0 (approved 69.4), K. Williams 45.9 (55.9),
J. Allen 31.2 (33.9), A. Jones 4.9 (9.7), Goedert 3.7 (2.6), Hockenson 3.6 to 4.1 (2.3). Find the cause in the code path
or the fixture, propose a fix with before/after, change no value math. (2) Switch bugs: Team 2's total with the switch off
was 253.2 after a flip but 225.1 after a reload; per-player lines did not redraw on a flip. Fix them with a test that fails
before and passes after.

### Finding 1: cause of the standard-bench gap (no value math is wrong)

The live standard bench was priced at the site's default league settings (PPR, QB1 RB2 WR2 TE1 FLEX1, 7 bench), not
USO's (half PPR, 3 WR, 5 bench). Settings that arrive through a league import or a share link are applied with
`TradeValueV2.applyLinkLeague` (`app/v2/league.js` applyImported and the share-hash reader), which deliberately does not
save them (`app/v2/v2.js` applyLinkLeague sets the input source to "link"; only the settings form calls
`saveLeagueSettings`). The saved league keeps them in `workspace.settings.query`, but nothing applies that query again on
a fresh load, so a reload restores the browser's saved settings (none, so the defaults). The engine, the references and
the fixture are consistent.

Six players, JS engine in the page at 760a1cb9 on its committed inputs, CBS visible (as on live):

| Player | Live (reported) | Before: default settings (what a reload prices) | After: USO settings kept | Approved table (fixture, 9614452c inputs) |
| -- | -- | -- | -- | -- |
| Jaxon Smith-Njigba | 67.0 | 67.0 | 69.6 | 69.4 |
| Kyren Williams | 45.9 | 45.9 | 55.8 | 55.9 |
| Josh Allen | 31.2 | 31.2 | 33.0 | 33.9 |
| Aaron Jones | 4.9 | 4.9 | 9.1 | 9.7 |
| Dallas Goedert | 3.7 | 3.7 | 2.6 | 2.6 |
| T.J. Hockenson | 3.6 to 4.1 | 4.1 | 2.4 | 2.3 |

The same run at USO settings, league levels (DDF / market): JSN 72.2 / 72.6, K. Williams 58.7 / 51.6, J. Allen 38.7 /
35.0, A. Jones 4.7 / 7.5, Goedert 4.2 / 4.1, Hockenson 3.6 / 3.6 (approved 71.4/72.9, 58.8/51.9, 40.7/36.2, 5.4/8.0,
5.3/4.0, 4.6/3.5). The remaining gap to the approved table is the inputs refreshed since 9614452c: the page's engine on
the fixture's frozen inputs reproduces the approved table exactly (below).

Proposed fix, for Jeremy (product choice, not applied): (A, recommended) save the league's settings when a league import
or share link applies them, as the settings form does, so a reload keeps them; (B) re-apply `workspace.settings.query`
when the league page loads; (C) apply nothing, show a "this league uses other settings" notice with a button, like the
team-count notice. A and B touch `app/v2/v2.js` or `league.js` page state only; no value math changes.

### Finding 2: switch bugs

- Lines not redrawn: the switch's store update has reason `league-rosters`, which `refreshAll` did not treat as a change
  to the numbers, so each team's player list (redrawn only when its entries change) kept the other level's values. Fixed:
  `league-rosters` clears every team's last-drawn entries, and the switch starts the trade search with a fresh pairing
  cache.
- Totals (253.2 after a flip, 225.1 after a reload): same cause as finding 1. The flip keeps USO's settings; the reload
  falls back to the defaults. Team 2's standard total at the default settings in a local build is 222.77 (225.1 on live,
  newer data). It is fixed by the settings choice above, not by the switch fix.

### Verified (check named)
- Before/after table: `/tmp` Playwright probes on a 760a1cb9 build (`tests._league_render.browser_on_build`, installed
  Google Chrome), `TradeValueCurveHarness.runPipelineWith({hidden: [], setting})` at both settings and all three levels.
  The default-settings row matches all six live numbers to 0.1 (Hockenson 4.1, inside the reported 3.6 to 4.1).
- Code path equals the fixture: the page's engine run on `tests/fixtures/league_levels/uso.json` inputs, its
  `variant_live` lineup and USO settings gives 69.4/55.9/33.9/9.7/2.6/2.3 (standard) and 71.4/58.8/40.7/5.4/5.3/4.6 (DDF
  level), identical to the approved table. `tests/value_pipeline_driver.js` on the fixture gives the same.
- The local render server pins a CBS hold (`tests/test_v2_finder_render.py` `_built_dist`, JEG-881), so locally CBS is
  hidden (`hidden: ["cbs"]` captured at `ValueModel.runValuePipeline`); with it, the USO standard row reads
  67.6/53.2/33.8/9.5/2.1/2.5. Local render numbers are therefore not live numbers; the table above passes `hidden: []`.
- Settings lost on reload: the same probe applied USO settings with `applyLinkLeague`, seeded the USO rosters, reloaded:
  the engine came back at PPR, WR2, BN7.
- Switch fix: `tests/test_jeg1389_switch_redraw_render.py` (new). Without the `league.js` change it fails ("switched
  off, the lines still show the league level", e.g. 19.7 drawn where the standard bench is 21.4); with it, OK (1 test,
  RENDER_TESTS_REQUIRED=1, Google Chrome).
- With the change: test_v2_league_units 2, test_jeg1231_opponent_inclusion 2, test_league_levels_trades 5,
  test_jeg1249_league_site_render 4, test_v2_league_levels_render 2, test_v2_league_tables_render 2,
  test_v2_league_parsed_render 2 OK (render suites with RENDER_TESTS_REQUIRED=1 and Google Chrome). These ran on the
  branch base b5f35fca.
- After merging origin/main (e76bb3d3): test_jeg1389_switch_redraw_render OK; test_jeg1249_league_site_render
  test_league_to_compare_journey fails ("no Details button for <row id>"). It fails the same way on a clean origin/main
  374dc8f7 worktree, so it is a baseline red on main, not this branch. Candidate cause, not bisected: a750ca07 (#1033,
  JEG-1125, one "even" band), the only main commit since b5f35fca that touches app/v2/finder.js or trade.js besides
  b923c11d (2QB superflex values).

### Claimed, not confirmed
- That Jeremy's live session reached USO's settings by a league import or share link (the only paths that apply them
  without saving). His browser state was not read.
- That live had no CBS hold at 18:29 UTC; the default-settings row matches live only with CBS visible.
- `make validate` and the full suite were not run locally; CI runs them on the PR.
