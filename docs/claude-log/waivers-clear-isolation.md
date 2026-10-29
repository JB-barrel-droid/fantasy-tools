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
  the test, plus a `node` parse of each body).
- The test module imports, and its four page scripts parse (`node` `new Function`).
- `python3 -m unittest tests.test_waivers_clear_isolation_render` skips cleanly without Playwright (2 tests, 4 skipped subtests).

### Claimed, not confirmed
- Baseline pass and mutant failures in a real browser: this container has no Chromium (Playwright's download host is disabled),
  so the render run has to happen in CI or on a machine with a browser once the module is wired.
- `tests.test_render_sweep_coverage` lists this module as unwired until it is added to a Makefile run list (proposed line:
  `python3 -m unittest tests.test_waivers_clear_isolation_render` next to `tests.test_waivers_render`). That test is already red
  on main for four other unwired modules.
- From reading the code (not observed): after roster Clear the Clear button hides and the input it focuses is still folded, and
  after roster Undo the roster folds again, so keyboard focus may land on the page body both times. The test records focus at
  both points as notes instead of asserting, since that would be new UX; it is for the JEG-1190 owner to confirm.
