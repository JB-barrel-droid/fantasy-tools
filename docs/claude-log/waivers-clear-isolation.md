## 2026-10-29 - JEG-1278 Waivers Clear isolation and shared-roster Undo (render test)

Contract: pin the shipped JEG-1190 promise on the Waivers tab with a browser test, no product change. Candidate Clear leaves the
roster, league teammates and settings alone and Undo puts the candidates back; roster Clear empties the shared roster, says so,
and Undo puts back the exact keys (kicker and defense included) without touching the candidates. 320, 390 and 1366 wide.

Files (all new): `tests/test_waivers_clear_isolation_render.py`, `tests/fixtures/waivers-clear-isolation.json`, this log.
No change to `app/v2/waivers.js`, `app/v2/workspace.js`, the Makefile, workflows or coverage wiring.

How it works: the fixture names players by position and DDF Value rank; the test resolves them to the build's real player keys
in the page, seeds a saved league (my team, two teammates, league settings snapshot) through the page's own workspace store,
writes the candidate list where Waivers reads it, and reloads on `#waivers`. Every step is driven by keyboard (focus, Enter,
Tab). Settings compared: the workspace's saved settings and ui, `ddf.v2.league-settings`, `TradeValueV2.leagueQuery()` and the
Waivers view choice. Requests that leave 127.0.0.1 during Clear/Undo fail the test.

Mutants (real source edits of `app/v2/waivers.js`, served in place of the file, each with a marker the page must report):
- candidate clear calls roster clear (`stores[target].set([])` -> `stores.mine.set([])`): must fail `cands-clear: roster changed`
- Undo restores the other list: must fail `cands-undo: candidates not restored`
- the roster's Undo writes into the candidates: must fail `mine-undo: roster not restored exactly`

### Verified (check named)
- Each mutant anchor matches `app/v2/waivers.js` at main 430791c exactly once and the mutated file still parses (`mutate()` in
  the test, plus `node --check` of each body; the diff of each is the one-line edit plus the marker line).
- The test module imports, and its four page scripts parse (`node` `new Function`).
- `python3 -m unittest tests.test_waivers_clear_isolation_render` skips cleanly without Playwright (2 tests, 4 skipped subtests).
- In a real browser (Mac session, 2026-10-29, Google Chrome 156.0.8078.48 headless via `CHROMIUM_PATH`, Playwright 1.63,
  `RENDER_TESTS_REQUIRED=1`, branch head d03affc1 on main 430791c): `python -m unittest -v tests.test_waivers_clear_isolation_render`
  ran 2 tests, OK, no skips. The baseline passes at 320, 390 and 1366 and reports no mutant marker. Each mutant reported its
  marker (so it was the file served) and failed its named assertion at 390:
  - candidate clear calls roster clear: `cands-clear: roster changed [16 keys, ending x:K:alex kessman, x:DEF:ARI] -> []`
  - Undo restores the other list: `cands-undo: candidates not restored [8 keys, ending x:DEF:BUF] -> []`
  - the roster's Undo writes into the candidates: `mine-undo: roster not restored exactly [the same 16 keys] -> []`
- Network: at page load the only request off 127.0.0.1 is `fonts.googleapis.com/css2`, which the hermetic resolver blocks (as in
  every render test). The test's network check starts after the seed check, so it covers Clear and Undo, which made none.

### Observed, for the JEG-1190 owner (recorded as notes, not asserted, since asserting would be new UX)
- At all three widths, after roster Clear, focus is on `body`; Tab reaches Undo within three presses.
- At all three widths, after roster Undo, focus is on `body` and the "Your roster is back." message is not visible (the
  roster folds again). Candidate Clear and Undo keep focus in the list and Tab reaches Undo, which the test asserts.

### Not covered here
- `tests.test_render_sweep_coverage` lists this module as unwired until it is added to a Makefile run list (proposed line,
  for the CI coordinator: `python3 -m unittest tests.test_waivers_clear_isolation_render` next to `tests.test_waivers_render`).
  That test is already red on main for four other unwired modules.
- A local built page with a seeded league; this does not establish live-site behavior.
