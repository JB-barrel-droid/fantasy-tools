## 2026-10-25 - FE finder lane (parent JEG-1093)

Contract: Find a trade front-end fixes from Jeremy's Mac review: JEG-1103, JEG-1094, JEG-1095, JEG-1098, JEG-1099.

### JEG-1103 Risers and Fallers duplicate DDF
Cause: the Risers picker passed every series in `TradeValueMovers.SERIES` to `renderSeriesPicker`, including `ddf_value_charts`, which is the same series as `ddf_value` (`sameAs`, JEG-1073) and carries the same label "DDF Value". Other pickers already hide it via `ddfPickKey`. Fix: Risers picker filters to pickable keys.
#### Verified (check named)
- `tests.test_v2_risers_render` passes; `check_picker` now asserts unique option labels; new mutation "duplicate DDF option in Risers picker" (filter removed) is caught by the checks (negative test).
#### Claimed, not confirmed
- Live site not reproduced; cause found from code.

### JEG-1094 two screens
Find a trade is now two routes: `#find-trade` (tab "Find a trade: your team", the one-roster finder) and `#find-league` (tab "Find a trade: league-wide", league, team summary and opportunities cards in a new `main#v2FindLeague`). Names are provisional (PMM pass is a separate ticket). The assessment table lives only in finder.js and is untouched (league uses the same finder code for fit and impact). Old `#find-trade?workspace=` league share links are rewritten to `#find-league?workspace=` in `canonicalizeHash`; plain `#find-trade` still lands on the one-team screen.
#### Verified (check named)
- `tests.test_v2_find_split_render` (new): each route shows only its own cards, own tab, own empty state, old share link moves; two mutations (both screens shown; league cards mounted on the team page) are caught.
- `tests.test_v2_polish_render` (new route assertions), `tests.test_v2_modules_render` (league cards on `#find-league`) pass.
#
### JEG-1095 what the league paste read
New summary panel `#v2LgParsed` (league.js `showParsed`), outside the folded import box: teams found, each team's name and roster size, which team is yours (updates when a star is pressed), lines that matched no player with the line text, plain error when nothing parsed or an ID load fails. Existing status text under the import box is unchanged.
- Finding: the parser reports an unmatched line only for ambiguous names and kickers/defenses; an unknown name is silently ignored, so "unmatched" will be short in practice. The test injects an unmatched line through `DDFRosterPaste.parseLeague` to check the display.
- Finding: a team named "Bye Week ..." is merged into the previous team by the parser (JEG-1110).
#### Verified (check named)
- `tests.test_v2_league_parsed_render` (new): 12-team paste, names and roster sizes shown, "no team marked" then the starred team shown as yours, injected unmatched line listed, bad paste shows the plain error; two mutations (summary never shown, unmatched lines dropped) caught.

### JEG-1098 top 10
`PAGE` 20 to 10; "Show 10 more", "Show all (N)", "Show top 10 only"; "Showing X of N" above the table (was a footnote). Throw-in dedupe already ran inside `findTrades` for every pairing (see JEG-885 comment); per-target diversity is a product choice, asked on JEG-885 as multiple choice, not built. The finder (one team) already caps at 10 (`LIMIT`).
Test changes, with reasons: `test_v2_league_tables_render` pinned 20 rows then 40 after Show more; the page size is now 10 by request, so it pins 10 then 20. Its row reader strips the "Both teams" button text from the trade cell (JEG-1099) and clicks Show all first where it needs every row (force-fit check). The "a missing piece is printed as null" mutation anchor was re-pointed at the new end of the same statement; same intent (a null child must show).
#### Verified (check named)
- `tests.test_v2_league_top10_render` (new): 20-team league, 10 rows and "Showing 10 of N" on open, keyboard Enter on Show 10 more / Show all, Show top 10 only, filtered count; three mutations caught (opens on 20, count line dropped, Show all capped).

### JEG-1099 both teams below the table
Click a row (or its "Both teams" button, keyboard reachable) and `#v2LgOppPanel` opens under the list: both teams, gives and gets, best starting lineup by slot before and after in DDF Value and in the Trade chart average, starters and bench change, roster-space line, the fit sentence the row already had, Copy link, Close, Escape closes and returns focus. Selected row highlighted; pick kept in the address as `?trade=<opponent>~<give keys>~<receive keys>` and restored on load; survives Show all / Show top 10 only. The viability slot (`#v2LgOppPanelViability`) is present and says checks are not shown yet: no viability data exists in the finder rows (nothing from the viable-offers work is wired). The link reopens the trade only where the same league is saved (or with the league link's `workspace=` part).
#### Verified (check named)
- `tests.test_v2_league_oppanel_render` (new): click row 1, both sides, lineups, starters arithmetic, highlight, address, survives expand/collapse, reload restores, Escape closes and returns focus; three mutations (click ignored, Escape ignored, pick dropped) caught.
- `tests.test_v2_league_basis_render` re-pointed at the league-wide tab (the league moved from tab `find` to `league`).

### Checks run across the lane
Verified (named):
- Passed on the final branch: test_v2_risers_render, test_v2_find_split_render, test_v2_league_parsed_render, test_v2_league_top10_render, test_v2_league_oppanel_render, test_v2_league_render, test_v2_league_tables_render, test_v2_league_shared_roster_render, test_v2_league_basis_render, test_v2_inputs_status_render, test_v2_polish_render, test_v2_modules_render, test_v2_hamburger_nav_render, test_v2_a11y_render, test_v2_a11y_batch2_render, test_render_sweep_coverage; `make test-core` ran clean through to its last item (test_render_sweep_coverage), which failed only because the four new render modules were not in a Makefile run list; they are now in `test-render-extra` and that test passes.
- Test edits forced by this work, none loosening a check: `test_v2_hamburger_nav_render` LABELS (tab count 9 to 10, new names); `test_v2_league_basis_render` clicks the `league` tab; `test_v2_league_tables_render` (see JEG-1098 above).
- Red on origin/main 06c9be24, reproduced on a clean worktree, not caused here: `test_v2_league_phone_render` subtest "the sort selector is dead" is not caught (JEG-1111); `test_v2_league_live_render` `test_settings_apply_live_and_find_reprocesses` "[find] the page scrolled on a live update".
#### Claimed, not confirmed
- `test_v2_mobile_phase1_render` `test_phase1_guards_hold` fails on a 115x16 "Connect the to..." link on Player values; not compared against main, and it is not on a page this lane touched.
- Live site not opened; the Risers cause was found from code and the render test.
- Per-commit states (before the later tickets) were not run separately; the suites ran on the final branch state.
- `test_v2_contract_render` and the 12-combo sweep were not run (no chart or value code changed).
- With ten tabs the desktop nav wraps to two rows at about 1000 px wide (measured: 1 row at 1100 px and above, 2 rows and 170 px tall at 1000 px). Nav layout is the nav ticket's call.
