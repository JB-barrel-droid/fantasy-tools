## 2026-10-23 - JEG-995 typed search offers kickers and defenses (part of JEG-988)

Decision: Jeremy, 2026-10-23 (multiple choice): typed search in Find a trade offers kickers and defenses by name, added as unpriced
"Not evaluated" entries exactly like a paste.
Changes: `pipelines/build_v2_page.py` (`kdef_names_js`: writes `dist/v2/kdef-names.js` at build time, script tag + build step),
`app/v2/finder.js` (suggestion list searches engine rows plus the K/DEF choices with the page's one matcher, priced players first on a
tie; K/DEF suggestion carries a "Not evaluated" tag; pick adds `{key, name, pos, team}` with key `x:DEF:<team>` / `x:K:<name>`;
already-on-a-roster check also matches a pasted defense by team and a pasted kicker by name),
`tests/test_v2_finder_kdef_search_render.py` and `tests/test_v2_kdef_names.py` (new), `docs/risk-register.md` (GAP-FINDER-NO-KDEF-ROWS).
Untouched: the value engine, `players.json`, value-model.js, curve-widget.js, every ranking or value calculation. Nothing generated is committed.
Data source: 32 defenses = fixed list in `build_v2_page.DEFENSES` (checked against roster-paste.js's city/mascot table and team codes).
Kickers = `data/inputs/sleeper_identity_base.json` (Sleeper /players/nfl, refreshed Tue/Thu by the sleeper-identity-refresh workflow), position K
with a team (37 today). Refresh path: that workflow, then the next build. Gap: a free-agent kicker (Sleeper team empty) or a kicker signed
since the last refresh is not offered by typing; paste still works. The base marks 117 retired/old kickers active with no team, so a team is the only current signal.

### Verified (named checks)
- `tests.test_v2_finder_kdef_search_render` both tests OK (1440, 390, 320): list has 32 defenses and 25+ kickers; "chiefs" and a kicker surname
  suggest the entry with the tag, a priced player has none; combobox options, ArrowDown activedescendant, Enter picks; row shows
  "Not evaluated" with no chips; not addable twice or to both sides; Clear then Undo and Move keep it; Find trades gives identical trade
  lists and identical group/score text with two K/DEF per side vs none, and the engine rows' hash is unchanged; suggestions inside the box, no sideways scroll at 390/320.
- Negative proof: the guard test serves 5 broken finder.js builds (no K/DEF choices, tag dropped, duplicate check dropped, engine-looking key, pos dropped) and 2 broken name lists (defense misspelled, no kickers); each fails the check.
- `tests.test_v2_kdef_names` OK, incl. 6 broken inputs caught (team-less kicker, duplicate, 31 defenses, two defenses one team, invented defense, kicker missing).
- Regression, one file at a time under the render lock, all OK: finder_box, finder, finder_paste, finder_chips, finder_arrange, finder_eval, finder_import, a11y_batch2, name_search renders; waterfall render main check (Compare 1366x768 fit) OK.
- Unit: tests.test_v2_finder, _box, _fit, _groups, _import, _balance, _impact, test_v2_name_search, test_build_v2_page, node test_v2_roster_paste.js OK.

### Not verified / claimed
- `tests.test_v2_waterfall_render.test_guard_fails_on_broken_builds`, mutation "no wide verdict column on short viewports", fails; it fails identically on a clean origin/main worktree, so it is pre-existing and not caused by this change (not fixed here).
- Real phone devices (Chromium emulation only); full `make validate` not run (value lanes in flux).
- Kicker coverage depends on the Sleeper team field being current; not audited against a live roster.
