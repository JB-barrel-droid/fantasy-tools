## 2026-10-24 - JEG-1019 Find a trade: one roster assessment table and a natural-fit headline

Contract: Jeremy (2026-10-24): "When you give assessments of two rosters I want to see the assessment of values in a table. Right now
you're showing the text about it twice. Do it once. I want an immediate headline on if there is a natural fit for a trade or not."
Front end only (app/v2/finder.js, app/v2/v2.css, tests). No value, ranking, fit-rule, engine, `value-model.js` or `curve-widget.js`
change; no `make sync` (render tests rebuild dist/ in the worktree; generated files were not staged).

### What changed

- The generated evaluation sentences are gone from both places (under each full roster, and in the team summary above the results).
  One section, `#v2FindAssess`, sits under the Find controls and above the results; it appears as soon as both rosters have at least
  the league's starting slots at QB/RB/WR/TE (a partial roster says when it will appear).
- It is one real table: caption, `th scope`, no tab stops. Rows QB, RB, WR, TE, Bench subtotal, Total. Per team: counted players,
  over/under flag (DDF Value, plus "(market: ...)" when the Trade chart average reads differently), then starter and bench value in
  DDF Value and in Trade chart average. Phone: the table scrolls sideways inside its wrapper with the first column sticky; the page
  itself never scrolls sideways.
- Under the table, one line per team with what the table does not say: its single biggest imbalance, and (not evaluated) DEF/K.
- Headline `#v2FindFit` directly under the Find controls: "Add both rosters to see fit" (no data), "Press Find trades to see fit"
  (rosters in), "Natural fit found: N group(s)" with a jump link that focuses the first natural group, or "No natural fit between these
  rosters: the trades below are value-only or force fits" (no trades found: "...: no trades were found"; fewer than three charts:
  "Fit not judged ..."). N counts every group, from the labels the groups already carry; the headline resets when a roster changes.
- On phones Find now scrolls the headline (not the results) to the top.

### Verified (check named)

- tests/test_v2_finder_eval_render.py (rewritten; 1366x768, 1440x900, 390, 320; two scenarios, Yahoo vs ESPN with no natural group
  and the swap with natural groups): exactly one table, no "Based on ..." text, no old eval ids; rows and every per-position cell
  (count, flag, starters, bench, both views, both teams) equal an independent computation from the engine rows; total equals the sum
  of every valued player; headline text, N and jump target equal the listed groups; headline on screen after Find at 1366x768 and 390;
  headline returns to "Add both rosters" after Clear; first column sticky; no horizontal page scroll.
  Broken builds caught (7): old sentence reappears, second assessment above the results, headline missing, "natural" headline with
  none, "no natural fit" headline with some, table bench cells read starters, table total differs from the lineup.
- tests/test_v2_finder_balance.py (node): headline texts, biggest-imbalance rule; 2 new mutants.
- tests/test_v2_finder_impact_render.py: now requires the assessment table above the groups (roster-impact values still equal the
  independent lineup computation, so the table and the impact block share one source).
- Groups, edges, scores, order unchanged: node comparison of origin/main finder.js and this branch (findTrades + groupTrades, seeded
  9v9 3-for-3, 92 trades, 27 groups): identical JSON. Rendered Yahoo/ESPN size 3 (7 groups): identical group list, edges, fit labels
  and order before and after in the browser. The earlier 221-trade fixture was not available; this is a different fixture.

- Regression renders, each alone under the lock, pass: box, collapse, chips, arrange, groups, import, paste, kdef_search, finder,
  impact (updated), a11y_batch2; node: finder, fit, groups, impact, box, import, balance, rescaled_copy.
- Fail identically on a clean origin/main worktree (not caused by this change): test_v2_finder_fit_render guard "tier ordering off"
  (the Yahoo/ESPN fixture now has no natural group at size 3, so reordering is invisible: the guard is vacuous on current data) and
  test_v2_waterfall_render guard "no wide verdict column on short viewports".

### Not verified / claimed

- Real review rosters and the live site.
- Compare 1366x768 fit and the a11y suites are expected unchanged (Compare is untouched); see the PR for which render files were run.

### Review follow-up (PR #883 feedback, 2026-10-24)

- test_v2_finder_fit_render now runs both orientations (Yahoo mine / ESPN theirs: no natural group; ESPN mine / Yahoo theirs: natural
  and force groups, asserted present so the order check cannot go vacuous). The "tier ordering off" mutant is now caught (verified:
  2 passed). The earlier "pre-existing vacuous guard" finding is fixed here, not left.
- test_v2_finder_impact_render keeps full rosters (6 extra players for the short side) so the assessment table shows, and compares the
  table's starters, bench and total per team and view with the independent lineup, with the group card's impact-line "before"
  number, and with the independent sum of valued players. Two new broken builds (wrong total, starters reading the bench) caught.
- tests/test_v2_finder_search_unchanged.py: seeded synthetic 9v9 rosters (LCG seed 7), 3-for-3 (92 trades, 27 groups) and 2-for-2
  (12 trades, 7 groups); sha256 of every trade and group (members, edge, score, order) from origin/main equals this branch's. The
  "221-trade" fixture quoted from the JEG-972 entry was not kept; these fixtures are what was compared. 3 mutants caught.
- Waterfall short-viewport guard still fails on clean origin/main; untouched.
