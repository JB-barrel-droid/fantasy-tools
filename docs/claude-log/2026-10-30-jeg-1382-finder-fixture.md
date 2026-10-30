## 2026-10-30 - Find a trade guardrails test: a fixture that lists trades under the live rules (JEG-1382)

`tests.test_v2_finder_guardrails_render` went red on main at 137c5531 (automated rebuild + players.json bake; CI
run 40998469482, job 123877103233): with the shared PICK rosters (top 30 by DDF Value, alternated) Find a trade at
size 3 listed nothing and the test timed out on `#v2FindList > li`.

Cause (reproduced headless with the Python reference rows and the real `finder.js` `findTrades`): the bake moved
Brock Bowers 34.394 -> 34.444 and Justin Jefferson 34.442 -> 34.432, swapping ranks 20/21. Bowers, the only TE in
the 30, landed on "mine"; both 3-for-3 packages that clear the charts send him away, the keep-lineup check drops
them (TE have 0, need 1), and the list is empty. 2 trades before the bake, 0 after. Not #1178 (Natural fit only
labels and orders; its own v2-render passed) and not the USA Today hold (tests/_holds.py pins the test's holds).

Change: the guardrails test slides the top-30 window (offset 0 = the shared PICK, up to 10) until the page itself
lists a 3-player trade, and fails loudly naming the finder's output if none does. Every assertion is kept; the
finder, Natural fit and data are unchanged.

### Verified (check named)

- Headless repro of the cause (scratch scripts, not committed): `findTrades` total 2 at 137c5531^, 0 at 137c5531,
  sanityDropped 2.
- `python3 -c "import ast; ast.parse(...)"` on the test.

### Claimed, not confirmed

- The render result is CI v2-render's (no Chromium in cloud).
- `tests.test_v2_finder_render` (Makefile render target, not in CI) uses the same PICK and likely fails the same
  way; left for a follow-up on this ticket.
- Live impact (simulated 12-team league, all 132 pairs): Find a trade is not empty, but the USA Today hold thins it
  (size 2: mean trades per pair 103 -> 19.4); with USA Today unheld the bake data gives 118.5.
