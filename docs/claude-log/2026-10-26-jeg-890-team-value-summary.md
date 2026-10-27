## 2026-10-26 - JEG-890 team value summary for both pasted rosters (Find a trade)

Contract: finish JEG-890 on top of main — a team value summary card above the Find a trade results, once both
rosters are in: rows Starters / Bench / Total and QB / RB / WR / TE, columns DDF Value and the Trade chart average,
each compared chart on expand, a held chart named, missing values shown as "—" with the total marked "incomplete".

Work done by an OpenRouter deepseek-v4.1-flash run (T2/T3). Untrusted until a Claude T1 review re-reads the diff and
runs the gate.

### Verified (check named)
- `tests/test_v2_finder_teams.py` (node, pure) passes: `python -m unittest tests.test_v2_finder_teams`. Checks the
  DDF Total equals the sum of the listed players' DDF Value (200 on the fixture) and the QB+RB+WR+TE rows sum to it;
  starters/bench equal `lineupValue`; the fantasypros total is a partial sum marked `complete=false` with `missing`
  `['T2']` (a real 0.0 counts); a series nobody prices has value `null`, not 0; the Trade chart average is absent with
  fewer than 3 charts; the held chart `cbs` is not a series; the starters are the DDF lineup in every column (the
  market column reads the DDF lineup, it does not re-pick); SUPERFLEX and a roster shorter than the lineup.
- Same file, `test_checks_fail_on_broken_builds`: five mutations of `app/v2/finder.js` (a missing value counted as 0,
  an incomplete cell never flagged, the Total read from the starters, the chart average shown with too few charts,
  the starters re-picked per column) each fail the checks.
- `tests/test_v2_finder_teams_render.py` passes with `RENDER_TESTS_REQUIRED=1 python -m unittest
  tests.test_v2_finder_teams_render` (1366x768, 390x844, 375x667): the card shows with both rosters and without
  pressing Find trades; its DDF Total / Starters / Bench and Trade chart average Total equal an independent
  `getAllRows` computation; "Show each chart" opens per-chart columns whose totals equal the listed players' sums;
  the pinned fixture's held CBS is named "CBS Sports not compared" and is not a column; the two team blocks stack on
  a phone (375/390) with `scrollWidth - innerWidth == 0`; setting scoring to standard and dispatching
  `ddf:league-settings-changed` rebuilds the card from the new rows.
- Same file, `test_guard_fails_on_broken_builds`: three mutations (the two teams' numbers swapped, the held chart left
  unnamed, the card not rebuilt on a league change) each fail the render checks.
- No value math changed: the card only reads the engine rows (`teamSummary` adds `pickStarters` sums and
  `withChartAverage`), so no 12-combo curve sweep was run. `node --check app/v2/finder.js` passes.
- Existing finder tests `tests.test_v2_finder_impact`, `tests.test_v2_finder_groups`, `tests.test_v2_finder_balance`,
  `tests.test_v2_finder_box` still pass unchanged.

### Claimed, not confirmed
- `make validate` / the full suite was not run (only the finder tests above). The render tests
  `tests/test_v2_finder_eval_render.py` and `tests/test_v2_finder_impact_render.py` fail on this branch, but they
  fail the same way on clean origin/main with the source changes stashed (a stale `#v2FindAssess` table assumption),
  so the failures are pre-existing and not from this change; another worker is fixing those render tests.
- Placement: the summary card sits after the roster assessment table and before the results in `#v2Find`. The ticket
  note ("the existing team-value line") refers to the card from JEG-972 #875 commit 3, which #883 replaced with the
  assessment table, so this is a new card beside it, not an edit of it.
- The card id is `#v2FindTeamSummary`, not the spec's `#v2FindTeams`: an existing render test
  (`tests/test_v2_finder_eval_render.py`) asserts no `#v2FindTeams` element exists.
- Open product question 5 (chart average with fewer than 3 charts) is not decided; the card follows main's
  convention ("n/a" column, note "Trade chart average: not enough charts this week"), not a new choice.

### Merge-wave review (2026-10-27, Ba-Nana run, Claude T1)
- Verified (diff read): `teamSummary` and `renderTeamSummary` only sum existing engine values (`pickStarters`,
  `withChartAverage`); no value math changed. Merged origin/main in, no conflicts.
- Verified (`tests.test_v2_finder_teams`, `tests.test_v2_finder_teams_render`, `tests.test_v2_contract_render`):
  the render test failed after the merge-in from main's JEG-1152 clock drift; fixed by adding
  `_render_env.pin_data_week_script()` like main's other render tests. Test change only, no assertion changed.
