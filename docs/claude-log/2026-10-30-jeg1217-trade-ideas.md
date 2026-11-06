## 2026-10-30 - JEG-1217 manager-aware trade ideas (PR #1084)

Contract: add a Managers card where you mark how each leaguemate trades, and a Trade ideas card on Find a trade
that re-reads Trade opportunities through those marks. Ideas are ranked by your gain, with Jeremy's likelihood
scale (Likely, Possible, and Long shot as stretch offers). No value, fit or Trade opportunities number changes.

Decisions (Jeremy, relayed through the coordinator): appeal blend A, bands A, rank by "your gain" with a likelihood
scale. On 2026-10-29 he added: "I just didn't want text boxes for how my leaguemates trade, and set everyone to
default initially". So the note box is now six checkboxes (Likes rookies, Wants draft picks, Win-now, Rebuilding,
Slow to reply, Rarely trades), all unticked for every manager. Smaller picks are in `docs/picks-log.md` and the
project picks log.

Change:
- `app/v2/manager-profiles.js` and `manager-profiles-ui.js`: the Managers card, its store and the fixed tag list
  (no free-text input). JEG-1255 later kept legacy notes as read-only.
- `app/v2/manager-recs.js` and `manager-recs-ui.js`: the Trade ideas engine and card. They mount themselves after
  the Managers card and redraw when Trade opportunities, a profile or the league changes, so `league.js`,
  `opportunities.js` and `workspace.js` are unchanged.
- `app/v2/manager-profiles.css`, `pipelines/build_v2_page.py`, `Makefile`, `.github/workflows/v2-render-test.yml`:
  wiring for the new files and tests.

### Verified (check named)
- `python3 -m unittest tests.test_jeg1217_manager_profiles tests.test_jeg1217_manager_recs`: 6 tests OK on
  954f445. Each test runs its Node harness and then source mutations that each must fail. The mutations include
  free text accepted as a tag, tags starting ticked, ticked tags not saved, and ticked boxes left out of Why.
- `tests.test_jeg1217_managers_render` (Playwright): passed in PR CI on 777bee0, with every check green. Independent
  reviewers also passed it locally at 888366c and 954f445, at desktop and phone widths.
- Independent Claude reviews on #1084 passed at 0a6fcbe, 888366c and 954f445. Each merge of main kept both sides
  and left the PR diff at the same 14 files.

### Claimed, not confirmed
- Ideas only re-rank the existing Trade opportunities rows. A wider search needs a change in the opportunities
  search (the #1072 owner), and that isn't checked here.
- A reviewer saw that Trade opportunities edges on the 4-team fixture are the same under Standard, Half PPR and
  PPR, on this branch and on main. That comes from main, not this PR, and nobody has looked into it yet.
