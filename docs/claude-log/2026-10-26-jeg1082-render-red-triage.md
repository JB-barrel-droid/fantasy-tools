## 2026-10-26 - JEG-1082 two render tests red on clean main

Contract: run `tests.test_v2_targets_render` and `tests.test_v2_names_render` on a clean worktree off origin/main (6ff94e89) and fix whichever named defect reproduces.

Done by an OpenRouter deepseek-v4.1-flash run (T2/T3, untrusted until a Claude T1 review). No code change was made: neither part's named defect reproduced as described.

### Verified (check named)
- Part 2 already green on 6ff94e89. `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_names_render` → `Ran 2 tests ... OK` (39.5s). Both `test_names` and `test_guard_fails_on_broken_builds` pass, so the "definition changed" mutation at `v2.js:6524` is caught on this revision. No change needed.
- Part 1 named symptom (the 1024x768 horizontal page overflow, 28px) is not present on 6ff94e89. `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_targets_render` fails with exactly one error, and it is not an overflow: `[1366x768] sell top 5 ends at 1153.4375px, below the 1110px fold at 1366x768 (JEG-461)`. `check_layout` runs `overflow` for every viewport in FULL ((1440,900),(1366,768),(1024,768),(390,844)); no `horizontal page overflow` error appears at 1024 or anywhere else, so the horizontal fix from JEG-1056/JEG-1106 is holding.
- Independent probe of the built `dist/` (throwaway Playwright script under /tmp, desktop 1366x768): `document.documentElement.scrollWidth - innerWidth == 0`; nav is 64px tall; the sell table's 5th `tr[data-player-key]` bottom is ~1133px, over the 1110px TOP5_FOLD_PX budget.

### Claimed, not confirmed
- The remaining Part 1 red is a vertical fold regression (JEG-461/JEG-675 spec: top 5 of both lists end by `TOP5_FOLD_PX`, currently 1110), not the horizontal overflow the ticket describes. Row heights at 1366 are 86-106px (two-line rows, #639); no CSS change was attempted because the ~45px has to come from a page-layout decision (title/check/filter/row height) that is not mine to pick, and I could not verify a fix within budget.
- Test docstring drift: the module docstring still says `TOP5_FOLD_PX (1060)` while the code sets `1110` (`tests/test_v2_targets_render.py:137`). Doc/code mismatch, unrelated to runtime behaviour.

### Open questions
- Part 1 needs a decision: is the 1366x768 top-5 fold a fresh regression to fix in `app/v2/v2.css` (which element gives up ~45px?), or is the 1110px budget to be revisited? Neither was authorised by JEG-1082's text, so both are left open.
