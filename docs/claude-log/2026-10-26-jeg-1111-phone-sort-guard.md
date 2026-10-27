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
  — OK before the change (mutation already caught); the anchor is live (assertNotEqual stale-anchor guard passes).
- Diagnostic (not committed, `/tmp/diag.py`): the dead-selector mutation yields the four
  sort-specific errors above at each width.
- Diagnostic (`/tmp/diag2.py`): team sort is ascending on the real build; every other mutation
  still produces its own error.

## Claimed, not confirmed
- The full-module and real-build runs after the edit were not re-run inside the budget. Before
  the edit, `test_phone_contrast_keyboard` failed on `[320px] sideways scroll by 24px`, caused by
  `#v2LgFilterFit` (the "Natural and market supported" option added by JEG-1093, e696bf25) having
  no phone max-width — app CSS, outside this ticket's scope. That real-build failure is not fixed
  here.

## Open question for Jeremy
The real-build phone check is red on `origin/main` from the JEG-1093 filter-label regression.
That needs its own ticket (app CSS), not this one.
