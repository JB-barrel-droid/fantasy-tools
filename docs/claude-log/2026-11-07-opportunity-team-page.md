## 2026-11-07 - JEG-1558 opportunity read on the team page (part 2 of 2)

Contract: team.html shows how big the reader's best move is (Big opportunity / A real opportunity / A small edge /
No meaningful move right now). Beside it: a "Where to look" slot gap, the waivers line when no pickup beats the bench,
and an (i) that says how the read is sized and where the lines came from. All numbers come from
DDFOpportunity.computeTeam (module from part 1). That runs the find.html trade search (DDF.find.searchPartner: your
valuation DDF, theirs Analyst charts, 1- and 2-player sides; natural fit only; partners are the league's other teams,
never waivers) and the Waivers tab's pickups (DDF.find.pickups on the entered list, else the league's available
players). Each move counts only above its own noise floor.

Decisions (Jeremy, 2026-11-07): thresholds 3 / 6 / 10% plus the noise rule; trades that fit both rosters only; the
hole is "where to look", outside the tier; ship on this snapshot. The thresholds come from one week of three Yahoo
half-PPR 12-team leagues. The page's (i) says so, and the re-check is JEG-1562.

JEG-1557's caveats note (caveats.js, #1350) landed while this PR was open. The best-move caveat is now one line in
that note's `.ddf-caveats__slot` ("Best move size: a guide set from one week of three 12-team half-PPR leagues. The
other team decides what it accepts."), set once a read exists. The placeholder slot was removed, so nothing is copied.

Found while testing: computeTeam kept the move with the biggest raw gain, even when that move was under its own noise
floor and a smaller move beat its floor. The render parity test caught it (ppr/10/SF: the waivers line showed while a
pickup of 1.63 beat its floor). Fixed in both PRs: the best counted move wins.

### Verified (check named)
- Tier, shown percent and waivers line equal an independent in-page oracle. The oracle uses TradeValueWaivers.netOf,
  DDF.find.searchPartner and DDF.find.pickups directly, without ddf-opportunity.js, and the tier rule is recomputed in
  Python. Covered: 3 settings (half PPR 12, PPR 10 SF, standard 12) at 1440 and 390, plus two more "my team" picks;
  big and marginal reads occur; no overflow; no banned reader text. Test: `tests.test_team_opportunity_render`.
- The same check fails with the big line moved to 11%: `test_guard_fails_on_shifted_threshold`.
- The existing team / explore / partners and find parity still pass: `tests.test_team_engine_parity`,
  `tests.test_find_engine_parity`, `tests.test_build_root_pages`, `tests.test_next_preview`, `tests.test_ddf_opportunity`.
- Desktop (two columns, "Where to look" beside the read) and phone (stacked) were checked by eye from Playwright
  screenshots of the seeded synthetic league.

### Claimed, not confirmed
- Medium and none reads are covered by the unit tests only. The seeded league produced big and marginal.
- The live page after deploy: to be checked after merge.
- The full trade search adds about 0.1 to 0.5 s after the page shows. It runs after first paint and shows "Sizing your
  best move…" meanwhile. Not timed on a phone.

### Review fixes (independent review on 438cee3a9)
- Exclusions: skipped teams and held players are left out, as on find.html, and the line says so. Verified by the render
  test's exclude run (my team 11, two teams skipped, two best players held): the read changed (5.6% to 4.9%) and
  matched the oracle.
- Waivers line, three cases:
  - "nothing available beats your bench" only when no pickup adds more than 0.05;
  - "within the normal noise of the values" when a pickup gains but does not beat its floor;
  - hidden when the waivers script is missing.
- "Where to look" names the slot in words, gives the gap in value units and says the analyst charts are used. The (i)
  says the gap uses the analyst charts and the tier uses DDF Value.
- One search per league state (cached), with a pause between partners so the page stays responsive.
- The render oracle still uses the same finder/find functions. Those functions are the engine under test elsewhere; the
  part under test here is the page's counting and copy.
- Delta review on 6d9094195: no waivers line on an unsized read; the note names the page "Pick trading partners". Render test and team parity rerun: pass.
- Merged main with JEG-1557. The render test also checks the best-move line in the caveats note. Render test, team parity,
  `tests.test_jeg1557_mobile_connect` and `tests.test_ddf_opportunity` pass on the merged tree.
