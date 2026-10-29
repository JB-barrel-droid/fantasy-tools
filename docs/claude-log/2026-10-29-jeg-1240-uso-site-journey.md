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

## 2026-10-29 - JEG-1264 correction (review f58ed5d1 on #1110 @ `7c45a47`)

Supersedes the first round's counts above (9 checks, the Node classes in the render file, the broad guard catch).
Files: `tests/node/uso_site_journey_contract.cjs` (rewritten), `tests/test_uso_site_journey_contract.py` (new: Node
classes), `tests/test_uso_site_journey_render.py` (browser only), `HANDOFF.md`. No app, Makefile, coverage or workflow
file. The fixture is unchanged and still says synthetic, shape only.

What changed, per finding:

1. Guard: the browser journey records each stage as read or blocked with a code; a page or script failure outside a read
   raises `HarnessError` and is never a finding. `test_guard_fails_on_a_link_without_get` runs the build and the mutant,
   requires both picks' league -> Compare stage read on the build with no `package-changed`, the same stage outcomes on
   the mutant, `package-changed` among the mutant's new codes there, and nothing new outside package loss and its
   repricing.
2. Self-supplied context: destinations are built on their own state, the same device (a deep copy) and another device
   (PPR, 10 teams, WR 2, BN 7, FantasyCalc-only basis, CBS unavailable, its own saved league with Team 05 as my team).
   Modeled values are salted with settings, basis and level and price a chart only where the device has it, so a lost
   piece moves numbers. Sources use the JEG-1259 `{status, reason, version}` shape (the browser reads
   `getSourceInfo()`); the pair link destination reruns its own search on its own values. Negatives: scoring, basis,
   held CBS, level, substituted team, missing team and emptied get each fail with their own code, on the equal and the
   2-for-1 package. `judge()` accepts a hold only when it names a reason for every lost piece and something was lost.
3. Pair finder and readouts: the Node envelope carries both sides' starters by slot and bench, before and after, from
   `trade-readout.js` (JEG-1260) when app/v2 has it, else finder.js `rosterImpact` (checked equal). The browser adds the
   pair finder (saved-team pickers, the listed group ticked to the exact package, aria-label values, its own lineup
   tables, starters only since it draws no bench rows), its own share link and Compare's address on another device.
4. Wiring: not on this branch. The infrastructure owner (`be/ci-regression-wiring`, per JEG-1264 comment 09600170) wires
   the classes below. No `KNOWN_RED`, no skip marker added.

Commands for the wiring owner:

```
# gating, green on main
python3 -m unittest tests.test_uso_site_journey_contract.UsoJourneyHarnessTest tests.test_uso_site_journey_contract.UsoJourneyMutationTest
# visible, expected red until JEG-1259 carries the context or holds the trade
python3 -m unittest tests.test_uso_site_journey_contract.UsoJourneyContinuityTest
python3 -m unittest tests.test_uso_site_journey_render
```

### Verified (check named)

- `python3 -m unittest -v tests.test_uso_site_journey_contract tests.test_uso_site_journey_render` on this branch (main
  `6be60d2` merged in): `UsoJourneyHarnessTest` 2 ok, `UsoJourneyMutationTest` ok, `UsoJourneyContinuityTest` 3 FAIL
  (expected), the 3 browser tests skipped (no Chromium). About 5 s.
- Node contract facts on main: 3397 candidates, 434 send JSN, across 11 opponents. Equal pick
  `team-o-05|1338,3247|3993,2791`, throw-in pick `team-o-06|3315,3247|1029,2140` (throw-in `receive:2140`), explicit
  2-for-1 from it.
- Continuity on main, by code:
  - state link: same device clean; another device `basis-changed`, `sources-changed` (CBS) and the repricing.
  - pair link: same device clean; another device `basis-changed`, `sources-changed`, and for the equal pick
    `package-not-rediscovered` (its own search on its own values does not list the package).
  - transfer: `context-missing` on every case (no trade-context.js).
- Mutations (each compared case by case with the build): search capped at 10 fails only
  `test_jsn_discoverable_in_the_uncapped_search` ("none truncated"); the DDF state link without `theirs=` adds
  `team-missing` on same-device state-link cases and nothing outside repricing; the pair link without `theirs=` adds
  `team-missing` on same-device pair-link cases plus package loss and repricing only.
- Same contract on app/v2 of each dependency head merged with main (scratch `git merge-tree`, read only):
  - #1086 `8599560`: harness green; transfer check passes. receive() returned ok with the carried rosters on the same
    device and a hold naming `sources-changed`, `rows-changed` on another device, for all three picks. State and pair
    links stay red as on main.
  - #1088 `b18c503`: harness green with the readout from `trade-readout.js` equal to the lineup math; continuity as on
    main.
  - #1105 `5427971`: harness green; continuity as on main.
- The seven in-page browser scripts parse (`new Function` in Node); the readout label parser handles "Name 12.3",
  "Name no value" and "empty".

### Claimed, not confirmed

- No browser test has run anywhere: no Chromium in this container (the Playwright download is refused by the proxy) and
  the module is not wired, so CI does not run it. Selectors (pair pickers, group checkboxes, the pair lineup table
  captions, Compare panels) are written from the source.
- Expected on main once it runs, from reading the source: league -> Compare `team-substituted` (Compare's default
  opponent) with `gains-missing` / `readout-missing`; Compare elsewhere `team-substituted` (its address carries no
  rosters). The pair finder may not list a league pick when its group ranking folds it; that would show as
  `package-not-listed`, a finding, not a harness error.
- The browser's other device differs in settings, basis and saved league but not in sources (the page offers no way to
  switch a source off); the Node contract covers source loss.

## JEG-1304 correction (bench-level scopes), 2026-10-29

Finding: `level(scope)` was called with route hashes (`#find-league`, `#compare-trade`, `#find-trade`) that match no
element, so every destination read `modeled` whatever the page drew. Fix in `tests/test_uso_site_journey_render.py`
only: scopes are the real views (`LEVEL_SCOPES`: `#v2FindLeague`, `#v2Compare`, `#v2FindTrade`), the marker may sit on
the view or inside it (#1147 puts it at `#v2CConstruction[data-bench-level]`, inside `#v2Compare`), and a scope that
matches nothing is `HarnessError` code `level-scope-missing`, never `modeled`. No page, value or wiring change.

### Verified (check named)

- `LevelScopeTest.test_every_level_scope_is_an_element_in_the_shell`, run against ebb96a0's in-page scripts: FAIL,
  `['#find-league', '#compare-trade', '#find-trade']` match no element in `app/v2/shell.html`. On the corrected head:
  pass.
- `LevelScopeTest.test_a_missing_scope_is_its_own_harness_code`: pass (ebb96a0 had no such code; its `level()` returned
  `modeled`).
- ORIGIN, DEST and PAIR parse in Node; `level()` on a fake DOM returns the inner marker, `modeled` for a view with no
  marker, and `{missing}` for `#compare-trade`.
- `tests.test_uso_site_journey_contract`: unchanged, 3 expected continuity reds.

### Claimed, not confirmed

- `UsoSiteJourneyRenderTest.test_level_reads_the_rendered_view` (browser) has not run: no Chromium here and the module
  is not wired into CI. Needs a Mac run.

## JEG-1304 follow-up: the Mac's panel-missing (settings lost on reload), 2026-10-29

The Mac ran the browser module at c4c213b: the three new checks pass, the three journey tests fail on
`panel-missing` after `?trade=` and reload, and on `candidate-missing` (one JSN candidate, none with a throw-in).

Cause of `panel-missing`, read from the source: the journey set scoring, teams and roster slots on the engine directly.
The page saves league settings to localStorage (`ddf.v2.league-settings`) only from its settings form
(`saveLeagueSettings` in v2.js), and restores from there on load. So the reload fell back to the defaults (PPR, WR 2,
BN 7), the league page searched a different league, and the fixture-settings pick matched no row. That is the test's
setup, not the page. Fix: `SETTINGS` saves what it sets in the form's v1 shape; `require_settings()` raises
`settings-lost` if the page runs on other settings after the reload or before the first read. Branch brought up to
main `7e01271` (#1086); HANDOFF.md conflict kept both entries.

### Verified (check named)

- `SettingsSurviveReloadTest.test_the_save_key_and_shape_are_the_pages_own` on c4c213b's `SETTINGS`: FAIL (it
  saves nothing). On this head: pass, and it pins the key and `v: 1` to v2.js.
- `SettingsSurviveReloadTest.test_lost_settings_are_named`: the defaults against the fixture name `scoring`, `WR`
  and `BENCH`.
- `SETTINGS` and `SETTINGS_NOW` parse in Node. Contract on main `7e01271`: harness and mutation green; continuity 2
  red (the transfer check now passes with #1086 on main).

### Claimed, not confirmed

- The browser journey has not run on this head (no Chromium here). Expected: the league panel opens on reload.
- `candidate-missing` is not explained by the reload: it is on the first search, before any reload. The Node contract
  finds 434 JSN candidates on modeled values; the browser found 1 on published values. The message now gives the total
  found. If the Mac shows one JSN candidate on the fixture's settings, the throw-in stages need a decision.

## JEG-1332 correction: "Position" read as a lineup slot, 2026-10-29

The Mac's rerun at 5d4ebf3 reached the later stages for the first time, and four of them reported
`readout-changed ... at us before Position, us after Position, them before Position, them after Position`.

Cause: `lineup()` and `starters()` took `table.querySelectorAll('tbody tr')`. A selector is matched against the whole
document, and only the results are limited to the table. The league panel's lineup tables sit inside a row of the
opportunities table's `<tbody>`, so their `<thead>` row ("Position | Before | After | Change") matched too. It was
read as slot "Position" holding "Before" on the league page only. Compare and the pair finder draw their tables
outside any table, so every destination differed from the origin. The fix: `:scope > tbody > tr`, the table's own
rows. Also, `team-substituted` now says how many players two rosters share and no longer prints `undefined` when
another device's ids are dropped.

### Verified (check named)

- `LineupReaderTest.test_a_table_inside_another_tables_row_reads_like_one_alone` (Node, no browser:
  `tests/node/uso_journey_lineup_reader.cjs` draws a renderTable table alone and nested in another table's row) on
  5d4ebf3's `COMMON`: FAIL, the nested table reads `'Position': ['Before']`. On this head: pass.
- `tests.test_uso_site_journey_contract`: harness and mutation green, continuity 2 red (pair link, state link),
  unchanged. All eight in-page scripts parse in Node.

### Claimed, not confirmed

- The browser journey has not run on this head. Expected: no `Position` in any readout line. The equal pick's readout
  should then compare clean on the same device, unless the page really differs.

## JEG-1304 follow-up: the throw-in pick on published values, 2026-10-29

The Mac's 21:04 run found 12 trade opportunities on published values. One sent JSN, and none of the JSN ones had a
throw-in, so the throw-in stage, `test_unequal_deal_keeps_its_package` and the `get=` guard all stopped at
`candidate-missing`. Diagnosis on JEG-1304: the page and the Node contract run the same `runAll`/`findTrades`; the gap
is the values. Modeled values draw DDF Value and the charts separately, while on published values DDF Value is the
average of the adjusted charts, so few trades pass "you gain DDF and 3 of 4 charts are fair". Pick A (the coordinator's
pick, logged): the browser picks the throw-in candidate the way the contract's `pickOnce` already does, on real values.

- `CANDIDATES` throw-in pick: a JSN trade whose throw-in is not JSN, else any JSN trade with a throw-in, else any trade
  with a throw-in. It reports `jsnThrown` and `throwIns` counts, and `sendsFocus` on the pick.
- Throw-ins are now `"give:<key>"` / `"receive:<key>"` strings. Before, the pick kept finder.js's `{side, row}`
  objects. So the "throw-in is not JSN" check compared a string with objects and never excluded anything, and
  `unequal_deal`'s `split(":")` would have failed on the first throw-in pick it ever got.
- `pack` returns `null` for no pick, not `undefined`, so a missing pick reads the same in Node and in the browser.
- The `candidate-missing` messages name the counts. No page, value, Makefile or workflow change.

### Verified (check named)

- `CandidatePickTest` (4 tests, Node, no browser: `CANDIDATES` on a stub page whose search returned finder.js-shaped
  rows) on c8e936f's `CANDIDATES`: 3 errors and 1 failure. No throw-in pick when no JSN trade has one, and with JSN
  throw-in rows it picked the trade whose throw-in is JSN itself (`t3` over `t4`). On this head: 4 pass.
- `python3 -m unittest tests.test_uso_site_journey_render`: 13 run, 9 pass, 4 browser tests skipped (no Chromium).

### Claimed, not confirmed

- The browser journey hasn't run on this head. Expected on published values: the throw-in pick is a non-JSN trade
  with a throw-in, if the page's 12 include one (the reference values give 11 of 79), and the `get=` guard gets both
  picks.
