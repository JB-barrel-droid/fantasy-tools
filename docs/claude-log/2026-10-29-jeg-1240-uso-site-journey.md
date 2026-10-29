## 2026-10-29 - JEG-1240 USO site journey regressions

Contract (ticket JEG-1240, parent JEG-1220): a real-site journey on pinned anonymized USO-shape rosters. Read both
sides' starters and bench by position, keep JSN discoverable under the uncapped search, pick an eligible candidate
the page actually found, open it in Compare and in the pair finder, and require the same player values, settings,
basis, bench level, rosters and gains, then reload and share without silently substituting saved state. Do not
require JSN to be Natural, do not force a trade through viability gates, keep unavailable values unavailable. No
vacuous checks: nonempty players and candidates, exact package ids, an unequal package, and a mutation that drops
carried context and fails for the intended reason. Test files only; no app, Makefile or workflow change.

Files (all new): `tests/fixtures/uso_site_journey/build_fixture.py`, `tests/fixtures/uso_site_journey/league.json`,
`tests/node/uso_site_journey_contract.cjs`, `tests/test_uso_site_journey_render.py`.

Fixture: 12 teams, half PPR, QB 1, RB 2, WR 3, TE 1, W/R/T 1, SF 0, BN 5, K 1, DEF 1 (15 per team). Only that shape is
USO's: the `roster_slots` and `teams_count` #1105 recorded from the league settings on 2026-10-29. Rosters are a
deterministic snake draft of `data/fixtures/current/players.json` (as of 2026-10-29, active-roster skill players by
the ESPN half-PPR rest-of-season projection the file carries), with Jaxon Smith-Njigba (3247) swapped onto "My team".
K and DEF are `x:` entries. No USO roster, team name, owner or note is used. Values are never frozen in the fixture:
the Node contract prices with modeled rows (labeled "modeled" in its output), the browser test with whatever the built
page publishes for its pinned week.

### Verified (check named)

- `node tests/node/uso_site_journey_contract.cjs check app/v2 tests/fixtures/uso_site_journey/league.json` on main
  `ca51f2f`: 9 ran, 0 failures, about 0.6 s. Facts it prints: 2762 candidates, 326 sending JSN, across 11 opponents.
  Equal pick `...|1338,3247|992,243` (vs Team 08); throw-in pick `...|71,3247|1344,319` (vs Team 10, throw-in
  `receive:319`); explicit unequal deal derived from it: 2 for 1.
- `python3 -m unittest -v tests.test_uso_site_journey_render`: the two Node-contract tests pass, including
  `test_contract_catches_dropped_context`, which serves three broken copies of app/v2 and requires exactly one named
  failure each:
  - `opportunities.js` `limit: Infinity` to `limit: 10`: fails `test_jsn_discoverable_in_the_uncapped_search`,
    "vs Team 02: every qualified candidate kept (10 of 325), none truncated".
  - `ddf-state.js` without `theirs=`: fails `test_compare_link_keeps_the_trade_context`, `[team-missing]`.
  - `finder.js` pair hash without `theirs=`: fails `test_pair_link_rediscovers_the_exact_package`, `[team-substituted]`.
- Same contract on the dependency heads (app/v2 from each, read only):
  - #1105 `5427971`: 9 ran, 0 failures.
  - #1086 `8c677a2` and #1088 `b0551f5`: one failure each, the discovery check (10 of 325 kept). Neither head has
    main's `limit: Infinity` (#1072), so both need main merged in before this journey can pass on them.
- The five in-page scripts of the browser test parse (`new Function` in Node).
- `tests/test_render_sweep_coverage.py` now lists `test_uso_site_journey_render` as unwired. That guard was already
  red on main for three other modules (`test_interactive_trades_release_render`, `test_v2_compare_rosters_render`,
  `test_v2_finder_guardrails_render`); this adds a fourth until the wiring handshake below.

### Claimed, not confirmed

- The three browser tests (`test_journey_keeps_the_trade_context`, `test_unequal_deal_keeps_its_package`,
  `test_guard_fails_on_a_link_without_get`) have not run anywhere. This container has no Chromium (the Playwright
  download is refused by the proxy) and the module is not in the Makefile or a workflow, so CI does not run it either.
  The in-page selectors were written from the source, not from a running page.
- Expected on main once they run (from reading league.js and v2.js, not observed): the league page's "Open in Compare
  a trade" link carries only `give=` and `get=`, so Compare takes its default opponent (the first other team with
  players) and shows "This trade includes players outside the selected rosters", which this reports as
  `team-substituted` and `gains-missing`. Compare's own address carries no rosters either, so the share step in a
  browser whose saved "my team" differs reports `team-substituted`. Those are JEG-1229's (#1086) to carry; the tests are
  not adjusted to pass on main.
- After #1105 lands, the league page prices from league bench levels and Compare from the modeled bench (its own code
  comment says so). The journey would then name `level-changed` and possibly `value-changed`. Compare has no marker
  for its bench level; the test reads `data-bench-level` if JEG-1229 adds one, and otherwise reads Compare as modeled.
- The browser envelope compares DDF Value only (Compare shows one series per player and DDF-only lineups). Trade chart
  average values and market gains are compared in the Node contract only.

### Wiring handshake (not done here)

Proposed to Codex on JEG-1240: either add `python3 -m unittest tests.test_uso_site_journey_render` to a render-sweep
shard (and `test-render-extra`), or list it in `KNOWN_RED` in `tests/test_render_sweep_coverage.py` as `"JEG-1229"` until
#1086 carries the context. The Node part could also join `test-unit-modules`. None of these hunks is in this PR.
