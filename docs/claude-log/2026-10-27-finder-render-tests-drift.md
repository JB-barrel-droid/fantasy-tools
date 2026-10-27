## 2026-10-27 - Find a trade render tests drifted from the page and the week's data (JEG-1185)

Contract: get the four red Find a trade render tests green on current main without weakening them. Each failure was
traced to its cause first; only a test that was wrong was changed. No file under `app/`, `dist/` or generated output was
edited.

### Verified (check named)
- `tests/test_v2_finder_groups_render.py` (`RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_finder_groups_render`,
  2 tests OK, including `test_guard_fails_on_broken_builds`): the shared `PICK` dealt the top 30 by DDF Value alternately,
  which this week is all RB/WR, so no side had a QB or TE and the search found nothing. The test now has a local
  position-balanced `PICK` (QB, RB, WR, TE by position, unique names, 12 players per side). The shared `PICK` in
  `test_v2_finder_render.py` is untouched, so the other importers (`collapse`, `chips`, `impact`, `box`, `arrange`,
  `kdef_search`, `eval`) behave as before. Checked by running the failing page with the new pick: 3 groups listed.
- `tests/test_v2_finder_eval_render.py` (2 tests OK, mutation test included). Three stale pins, all behind intended page changes:
  1. The assessment table gained a "DDF Value (projections)" group (JEG-1081), so a team is 8 cells wide, not 6, and the
     Total row has 5 cells per team, not 4. The column offsets are now `TEAM_COLS = 8` and `TOTAL_COLS = 5`
     (the `float('OK')` error was the Flag cell of the second team being read as a number).
  2. The "no tab stops" check counted the new "Show projections" toggle button; it now looks only inside the `<table>`,
     which is what it was meant to pin.
  3. The no-natural-fit headline text was rewritten with the fit labels (JEG-1108, the "value" label is retired): the default
     sentence now says "market supported or force fits"; the assertion followed it.
- `tests/test_v2_finder_impact_render.py` (2 tests OK, mutation test included). Two stale parsers: the delta regex `[+\-\d.]+`
  did not accept U+2212, the minus sign the page prints (the formatters `fitFmt` and `sign` in `app/v2/finder.js`, uses it on purpose); the
  regex and the `float()` now accept and normalise it. Then the table reader required exactly 32 data cells and 4 totals,
  which broke when the projections group was added; it now reads only the `ddf-` and `market-` cells, the two views it checks.

### Claimed, not confirmed
- `tests/test_v2_finder_fit_render.py` is NOT fixed and was not changed. Its failures are not drift in a parser:
  CBS is held this week (Week 7 content against current Week 8, `getSourceInfo` shows `cbs.available = false`), so only
  three trade charts are available and the finder needs all three to say the rival breaks even or wins
  (`minCharts = min(3, charts)`). Observed in the built page: (a) the thin-roster case finds no star RB for two RB2s where
  DDF Value rises while all three charts are level or better (scanned every RB pair, then every player triple: none
  with 3 of 3; the best have 2 of 3); (b) in the ESPN-mine / Yahoo-theirs orientation only one group is listed, a
  natural one, so the "at least two different fits" guard has nothing to compare. This needs a decision, not a quiet edit:
  skipping these checks when fewer than 4 charts are available would weaken the guard, and the page behaviour is the
  documented one. Not confirmed: whether the same pass would come back on its own once CBS is current.
- The new groups pick is balanced by position, not guaranteed to produce a trade in every week; it fails loudly
  ("0 group cards listed") if a week has none, as before.

### Follow-up: fit test (JEG-1185, Jeremy's decision: synthetic rows for the thin case, four-chart build)

#### Verified (check named)
- `tests/test_v2_finder_fit_render.py` (`RENDER_TESTS_REQUIRED=1 python -m unittest -v tests.test_v2_finder_fit_render`:
  `test_fit` OK and `test_guard_fails_on_broken_builds` OK, so all five mutations, tier ordering off, fit line not drawn, tier order
  reversed, folded groups not counted, two-player packages not searched, are still caught).
- Root cause of the CBS part: the shared `_built_dist` pins CBS held (`tests/_holds.py`, JEG-675), leaving three charts. The plain
  committed fixture is worse (all four charts held, Week 7 against Week 8), so the fit test's own `_built_dist` applies the same pin
  and also clears the CBS hold in its own copy. Check: the new up-front assertion on `getSourceInfo` (fewer than four available
  charts fails and names the available and held ones), and the swapped-roster "two different fit labels" guard now passes.
- Thin-roster case: weekly data has no star RB with two real RB2s that DDF Value prefers while three of four charts price them level
  or lower (scanned every pair and triple, JEG-1185). The test injects three synthetic rows ("Test Star RB", "Test RB2 A", "Test RB2 B",
  keys 9000001 to 9000003) as data in its own build copy: clones of real RBs' player rows and per-source entries; the star's
  entries on the four charts set to the RB2s' sums, with CBS scaled so the DDF Value gap lands near 1.5 (DDF Value follows the charts).
  No finder or engine code is touched, no reader overrides. The `THIN` check asserts in the page that the rows arrived exactly once,
  are RBs, the RB2s are 8 or more, the gap is 0.2 to 4 and at least three charts are level or lower; a broken injection fails loudly.
- Two more stale pins were behind intended page behaviour (JEG-1108 throw-in rule), fixed in the test: the thin team is built with
  exactly its starting slots (a team receiving more players adds its cheapest bench player, which would swallow the 1-for-2 edge;
  a team with no bench leaves it listed); the in-page `findTrades` call now passes the same roster sanity and league shape the page
  passes (it lacked it, so every player counted as bench); the group card is found by a target that names either the better RB2 or
  both RB2s (the page names the whole received core).

#### Claimed, not confirmed
- The synthetic CBS factor is found per week from two builds and a straight-line fit; it is not proven to land in the 0.2 to 4 window
  every week. If it does not, the in-page assertion fails with the numbers instead of passing.
- This supersedes the "NOT fixed" bullet above for the fit test: the cause was the pinned CBS hold plus no real thin-roster pair,
  not a page fault.
