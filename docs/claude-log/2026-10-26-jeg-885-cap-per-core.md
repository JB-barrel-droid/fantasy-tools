## 2026-10-26 - JEG-885 cap 2 rows per received core player (league-wide opportunities)

Contract: the league-wide trade opportunities list showed the same received player nine times in its first ten
rows. Jeremy, 2026-10-25 (multiple choice, option B): "At most 2 rows per received player (the core player), the
rest folded under 'N more for <player>'." Apply that before the top-10 cut, presentation only.
Jeremy, 2026-10-26 (follow-up, option A): the cap applies only to the opening 10 rows; "Show 10 more" and "Show all"
show the plain ranked list; the one-team finder's groups stay as they are. The code already did this.

This work was done by an **OpenRouter deepseek-v4.1-flash run (T2/T3 output, untrusted until a Claude T1 review)**.

### What changed
- `app/v2/opportunities.js`: new pure `capPerCore(rows, keyFn, n)` and `CAP_PER_CORE = 2`. Keeps at most `n` rows
  per key in the order given and returns the rest as `folds` (key -> rows). Same row objects, same order: selection
  only. No change to `runAll`, ranking, fit labels, viability or `findTrades` math.
- `app/v2/league.js` (`renderOppsNow`): the open list caps at `O.CAP_PER_CORE` rows per received core player; each
  capped player gets a "N more for <player>" control (table row and phone card) that opens that player's remaining
  rows in place, `aria-expanded`, keyboard-operable (focus returns to it through `keepFocus`). Expanding past the
  first page ("Show 10 more" / "Show all") shows the plain ranked list; the count line stays "Showing X of N" with
  N = the ranked list. Row ids, ranks, values, edges and fit labels are untouched.
- `app/v2/v2.css`: two rules for the fold cell and the fold button.
- `tests/league_harness.cjs`: `test_opportunities_cap_per_core` (pure) and `test_opportunities_cap_on_a_fixture`
  (2-team fixture: one received player has 10 rows -> 2 visible, 8 folded, the two best in rank order).
- `tests/test_v2_league_units.py`: both checks named in `REQUIRED` plus two mutations that must fail them
  (`CAP_PER_CORE` 2 -> 3; the overflow never folds).
- `tests/test_v2_league_top10_render.py`: new `LeagueCoreCapRenderTest` on the same list — first 10 rows cover
  >= 4 received players, <= 2 rows each, no two rows the same trade up to players worth 0.0 on DDF Value and every
  compared chart, and the fold control opens/closes from the keyboard. Two mutations (cap switched off; fold
  control not drawn) must fail it, so the checks fail without the cap.

### Measured (20-team fixture league, the fixture closest to the "review rosters"; the audit's 14-man pair is not
in the repo)
- Before the cap (real built engine values): the first 10 rows covered **3** received players
  (Jordyn Tyson 1, Jakobi Meyers 6, Xavier Worthy 3) — the reported shape (nine of ten for one player).
- After the cap: the first 10 rows cover **6** received players (Tyson, Meyers, Worthy, Malik Washington,
  Jordan Addison, Zach Charbonnet) with 2 rows each at most; count line "Showing 10 of 111", the folded controls
  "5 more for Jordyn Tyson", "7 more for Jakobi Meyers", "6 more for Xavier Worthy", "8 more for Malik Washington",
  "8 more for Jordan Addison", "3 more for Zach Charbonnet".
- One-team grouped finder (measured with `groupTrades` on the 2/4/20-team fixtures): already one group per receive
  core for the common case; the first 10 groups cover 5 distinct received players on every fixture. The acceptance
  holds there, so it is **unchanged** (Jeremy, 2026-10-26, option A).

### Verified (check named)
- `tests.test_v2_league_units` (harness on the real modules + every mutation) passes, including the two new cap
  checks and the two new mutations.
- `tests.test_v2_league_top10_render` (4 tests) passes: the existing JEG-1098 checks and the new
  `LeagueCoreCapRenderTest`, with its two mutations caught (printed messages: "the first 10 rows cover only 3
  received player(s): {'Jordyn Tyson': 1, 'Jakobi Meyers': 6, 'Xavier Worthy': 3}" / "no 'N more for <player>'
  control ..." for cap off; the fold-control message for the second mutation).
- `tests.test_v2_league_tables_render` and `tests.test_v2_league_oppanel_render` (4 tests) pass — with the cap in
  place `test_v2_league_tables_render` still reads rank 1..n after "Show all", which is why the cap applies to the
  open list and the expanded list stays the plain ranked one.
- `tests.test_v2_league_phone_render` (2 tests) passes: the fold button is a `.v2-link` (44 px) inside the card of
  the player it belongs to, so the phone control-size and card checks hold.
- `tests.test_v2_league_render` (2 tests) passes on a re-run, and `LeagueRenderTest.test_team_list` alone passes on
  both this branch and clean `origin/main` 93920eb9.

### Claimed, not confirmed
- The live site was not opened; every number above comes from the headless render tests on the local build.
- `tests.test_v2_league_render.LeagueRenderTest.test_team_list` failed once with "[list] expand did not open the
  team" during a full-module run while this branch was being edited, and did not reproduce (standalone on this
  branch, standalone on clean main, and a full-module re-run all pass). Not compared against a main full-module
  run, so a rare flake in that check is unproven.
- The one-team grouped finder's 50%-heavy rule can still put more than 2 groups for one core player in its first 10
  (2-team fixture: 4 groups for Malik Nabers, 5 distinct cores in the top 10). The ticket says to leave the finder
  unchanged when the acceptance holds, and it does, so it was left alone; Jeremy confirmed that on 2026-10-26 (option A).
- The 20-team fixture is used as the stand-in for the audit's 14-man review rosters (no review-roster fixture is in
  the repo); no test here reproduces the audit's exact "McConkey for Egbuka" roster.

### Not done / open
- PRs #945 (JEG-1108 fit labels) and #960 (JEG-1129) also edit `finder.js` and `opportunities.js`. This diff does
  not touch `finder.js`; `opportunities.js` gains one new pure function and two exports, and `league.js` gains the
  cap block, so a rebase should be small.
- Pushing, PR, merge and deploy are the PM's; nothing was pushed.

### T1 review (Claude, Ba-Nana merge wave, 2026-10-26)
- Checked the code against both decisions: the cap runs only while `UI.oppsShown === PAGE`; "Show 10 more" / "Show all"
  slice the plain sorted list; `finder.js` and all value math are untouched. Merged `origin/main` in (no conflicts);
  updated the league.js comment and this log to cite the 2026-10-26 choice.
