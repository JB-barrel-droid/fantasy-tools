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
