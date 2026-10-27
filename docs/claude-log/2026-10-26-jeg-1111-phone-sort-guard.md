# JEG-1111 — league phone render: the "sort selector is dead" mutation

By an OpenRouter `deepseek-v4.1-flash` run (T2/T3, untrusted until a Claude T1 review). Test-only change.

## What the ticket claimed
`LeaguePhoneRenderTest.test_guard_fails_on_broken_builds`, subtest "the sort selector is dead",
returns no errors for the mutated build, so the guard misses the bug it names.

## What I found
The premise does not reproduce on `origin/main` today. With the anchor line
`sel.addEventListener("change", () => onSort(S.nextState({col: null}, sel.value, columns)));`
removed from `app/v2/league.js`, `caught(overrides, {"phone"})` returns four errors per width
(390/360/320), all about the sort: `the sort selector did not sort the summary by bench value:
['rank:ascending']`, `summary cards after sorting by team: [...]`, and the two opportunities
errors. The subtest passes, i.e. the mutation is caught. The discrimination the ticket asks for
(step 2) was already added on 2026-10-26 by commit 20c0c76a (the "sorting by team did not
reorder" check), so the ticket looks stale.

## What I changed (tests/test_v2_league_phone_render.py only)
- `check_phone`: the team-sort card check now requires the column's declared first direction
  (ascending, per `table-sort.nextState`), not "asc or desc", and asserts the visible first card
  is the alphabetically first team — the cards, not the hidden table's `aria-sort`, are the proof.
- `test_guard_fails_on_broken_builds`: a mutation may carry a phrase its caught errors must
  contain; the sort mutation must be caught by an error that names the sort selector, so the
  guard can no longer pass on unrelated noise (e.g. a layout error). No assertion loosened.

## Verified (checks named)
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_league_phone_render.LeaguePhoneRenderTest.test_guard_fails_on_broken_builds`
  — OK before the change (mutation already caught) and OK after it. The new phrase assertion is
  live: the dead-selector mutation is caught by an error that literally contains "sort selector"
  (`the sort selector did not sort the summary by bench value: ['rank:ascending']`), so the phrase
  is real and the anchor is live (the `assertNotEqual` stale-anchor guard passes).
- Diagnostic (not committed, `/tmp/diag.py`): the dead-selector mutation yields the four
  sort-specific errors above at each width.
- Diagnostic (`/tmp/diag2.py`): team sort is ascending on the real build (so the tightened
  direction assertion is safe); every other mutation still produces its own error.
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_league_phone_render` (whole module,
  branch tip) — 2 tests, 1 failure. `test_guard_fails_on_broken_builds` passes (all six mutations
  caught, the sort one by name). `test_phone_contrast_keyboard` fails on
  `[320px] sideways scroll by 24px`, the pre-existing app-CSS overflow below, unchanged here.
- Pre-existing overflow confirmed on clean `origin/main`: `git checkout origin/main --
  tests/test_v2_league_phone_render.py` then the same method fails with the identical
  `[320px] sideways scroll by 24px`, and the JEG-1111 diff touches no overflow code. Not hidden,
  not fixed here (app CSS).

## Claimed, not confirmed
- Nothing: the guard method and the whole module were both re-run after the edit, and the
  real-build overflow was reproduced on clean `origin/main`.

## Open question for Jeremy
The real-build phone check is red on `origin/main` from the JEG-1093 filter-label regression.
That needs its own ticket (app CSS), not this one.
