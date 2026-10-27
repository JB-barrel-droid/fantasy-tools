## 2026-10-26 - JEG-1082 two render tests red on clean main

Contract: make `tests.test_v2_targets_render` and `tests.test_v2_names_render` pass on a clean worktree off origin/main (6ff94e89), fixing the page where the ticket's named defects reproduce, without touching `TOP5_FOLD_PX` or any assertion.

Done by an OpenRouter deepseek-v4.1-flash run (T2/T3, untrusted until a Claude T1 review).

### Verified (check named)
- Part 2 needed no change. `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_names_render` → `Ran 2 tests ... OK` (39.5s) on 6ff94e89. Both `test_names` and `test_guard_fails_on_broken_builds` pass, so the "definition changed" mutation at `app/v2/v2.js:6524` (the line `syncBasisLabels` actually rewrites `NAME_DEFS[0][1]` from) is caught on this revision.
- Part 1: the ticket's named symptom (the 1024x768 horizontal page overflow) is already gone on 6ff94e89; the only failure was the vertical fold: `[1366x768] sell top 5 ends at 1153.4375px, below the 1110px fold at 1366x768 (JEG-461)`. `check_layout` runs its `overflow` probe at every viewport in FULL ((1440,900),(1366,768),(1024,768),(390,844)) and no overflow error was raised at any of them, so the JEG-1056/JEG-1106 nav fix holds.
- Part 1 fixed in `app/v2/v2.css`: a `@media (min-width: 1024px) and (max-height: 820px)` block scoped to `#v2Targets` trims the table cell vertical padding (8px → 3px), the player name / sub-line `line-height` (→ 1.2), the `.v2-tlist` top padding and the list-head meta margin. Nothing is hidden, no name is truncated, and the 900px-tall desktop is out of range so its fold check is untouched. Verified two ways:
  - throwaway Playwright script over the built `dist/` at 1366x768: the sell table's 5th `tr[data-player-key]` bottom moved 1108 → 1020px (rows 86-91 → 71-78px tall);
  - `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_targets_render` → `Ran 2 tests ... OK` (303s), both `test_rendered_numbers_and_layout` and `test_guard_fails_on_broken_builds` green, so the fold passes at 1366x768 and 1440x900 and the discrimination mutations are still caught. `TOP5_FOLD_PX` and all assertions unchanged (`git diff` touches no `assert`).
- Stale docstring fixed: `tests/test_v2_targets_render.py` said `TOP5_FOLD_PX (1060)`; the code sets `1110`.

### Claimed, not confirmed
- Row heights are data-driven (wrapped names / two-line sub-lines), so the 1366x768 fold had ~45px of headroom eaten by taller rows than the fixture the 1110 budget was measured on. The density rule buys ~88px, which is why it should stay green as the data moves, but only the single run above was observed.
- Only the named test modules were run. `make validate` / `make test-core` and the rest of the render suite were not run in this session.

### Open questions
- The `@media (min-width: 1024px) and (max-height: 820px)` density is my choice of trade (tighter rows on short desktops vs. any other way to buy the ~45px). If Jeremy prefers a different lever — trimming the "1. Potential mispricing" block or the title spacing instead — it is a one-block swap in `app/v2/v2.css`.
