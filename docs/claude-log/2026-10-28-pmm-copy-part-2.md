## 2026-10-28 - JEG-1130 (part 2): PMM glossary and empty states outside the hot file

Contract: carry on from part 1 (PR #1008) and apply the approved PMM doc (Jeremy, 2026-10-26; sections 2 and 3, Appendix A) to the strings left in the non-hot files. Copy only: no layout, behaviour, dist, audit-page or league-ID loader changes. Branch `muse/jeg-1130-pmm-copy`, draft PR.

Changed:
- Risers & fallers (doc 3.2): section headers Rising / Falling / Mixed signals, "The market moved first" / "The projections moved first"; the series picker label says "Change:" (glossary retires "Movement"); the subtitle is the doc's full line. The collapsed-card names in `modules.js` follow.
- Trade targets static copy: check 2 is "2. Positions the market overpays for" (doc Do/Don't); the check 1 subtitle says DDF Value and the market (Appendix A #1, #2); "In between is fairly priced" is "a fair price" (glossary).
- Value above waivers panels (Player values, Compare) and the Methodology card use the glossary definition and the term "Value above waivers" (Appendix A #3); Methodology drops "value budget" (A #11), "Our value." and "the rescaled trade charts" (A #1, #2).
- Compare: the deal grid summary is "How each lens sees it" (doc 3.4).
- Find a trade: the three view tooltips use the glossary definitions and name no publisher (Appendix A #8); the empty note and the no-trade note use the doc 3.3 empty states; a name search with no match uses the doc's "Can't find" line (also in Your league and Waivers).
- Your league: the team summary says Buy / Sell, not Undervalued / Overvalued (glossary), in the table headers (`team-summary.js`), the phone cards and the footnote; the trade opportunities line says "the market"; the league paste help ends with the doc 3.5 footnote.
- Test assertions updated only where the pinned copy itself changed (Jeremy's PMM doc changed the rule): `test_v2_contract_render`, `test_v2_disagree_render`, `test_v2_group_weight_render`, `test_v2_copy_names`, `test_v2_finder_triview_render`, `test_v2_league_tables_render`.

Deviations, left for Jeremy or later tickets:
- Series labels ("Trade chart average", "DDF Value (projections)") stay. The doc has two namings (glossary: DDF Value / Market / Projections; the Oct 26 2:38 PM FINAL update: DDF Charted Value / DDF Projected Value / The Market), and a rename needs `app/v2/v2.js` (hot file, open PRs #939, #967, #969, #970, #1012, #1023, #1035) plus about 25 test files in one change.
- Strings set at runtime by `app/v2/v2.js` stay: Value chart subtitle, Trade targets intro, Sell/Buy titles and footnote, Compare "No verdict yet" and empty line, the Mixed signals meta line, the error state, the "our value" strings and the publisher list in `basisPhrase()`.
- Nav labels and H1s (doc 3.2: Buy & sell, Check a trade, Settings, Show the math, "Risers & fallers") stay: Appendix B #3 is open and JEG-1138 / JEG-1139 rebuild Compare and Trade targets.
- Waivers "no pickup" headline stays: the expected text is pinned in `tests/fixtures/waiver-all-worse.json`, and a Muse branch does not edit fixtures (AGENTS.md).
- Methodology "Our estimate of what a player is worth" stays: it matches the v2.js names popover, and JEG-822's guard bans the glossary's "really worth" on that page. The finder tooltip uses the glossary sentence without "really" for the same reason.
- Audit pages (`audit-pie.js`), Overrides (`overrides.js`), the AI strip (PR #970 edits beside it), the notice priority order (behaviour) and the formula footnotes moving into a drawer (layout) are out of scope.
- No emoji from the doc's empty states (Appendix B #4 open on playful lines).

### Verified (check named)
- Done-when grep `git grep -i -E "works with|supports|connect(ed)? to|sync" -- app/v2`: nothing about Sleeper, ESPN or Yahoo.
- `python3 -m unittest tests.test_launch_copy_guard tests.test_v2_copy_names tests.test_v2_league_units tests.test_waivers_math tests.test_v2_disagree`: 12 OK.
- Every `test-core` module run one by one (93 unittest modules plus the 3 node scripts): 61 pass; the other 35 stop at the same environment error (Playwright cannot launch Chromium, so the `make sync` equivalent fails). None failed on an assertion. The generated `app/trade-value-chart` and `dist/` files the run rebuilt were restored with `git checkout` and the untracked dist files removed.

### Claimed, not confirmed
- Render tests (Playwright) were not run here: no Chromium in this environment. CI runs them.
- Before/after screenshots (desktop and phone) were not taken: no Chromium and no Deno here.
