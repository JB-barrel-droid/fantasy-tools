## 2026-10-28 - JEG-1190: clearing players and teams is easy on every screen

Jeremy asked that it be easy to clear players and teams from every screen, and that
Compare a trade be intuitive for someone arriving for the first time (it opened with a
sample trade already filled in).

### Audit (main at fde5b9e)

- Compare a trade: remove was a bare ✕; the sample trade's rows looked like a real trade
  and could not be removed one at a time; no way to clear one side; Clear trade had no undo.
- Waivers: Clear emptied the list with no message and no undo, and "Your roster" is the
  shared workspace roster, so it also emptied both Find a trade screens without saying so.
- Find a trade, league-wide: teams could be removed one at a time only; no clear-all.
- Find a trade (your team): no single control to empty both rosters at once.
- Overrides and Value chart: already fine (per-row remove plus clear-all).

### Decisions

- Compare starts empty with a "Try a sample trade" button (Jeremy picked option A on
  2026-10-28). This replaces the JEG-469 rule that Compare opens on the example, so the
  example tests changed because the rule changed, not to go green.
- The button copy is "Try a sample trade", from the approved PMM doc section 3.3, not the
  "Try an example" wording in the option label.
- Waivers keeps one Clear per list, with no "clear both": clearing candidates should never
  wipe the shared roster.

### Changes

- Compare: empty state "Who's on the table?" with Try a sample trade; the sample is marked
  Example and is editable; adding a player replaces an untouched sample; "Remove" text
  buttons; a "Clear side" link under each side; Undo after Clear trade or Clear side.
- Waivers: Clear says what it cleared (and that Your roster is shared) and offers Undo.
- League-wide: "Clear league" with a confirm that counts teams and players, then Undo.
  New pure op `W.ops.clearLeague`.
- Find a trade (your team): "Clear both" in the arrange toolbar, with the existing Undo.

### Verified (check named)

- `node --check` on every app/v2/*.js: pass.
- `tests/league_harness.cjs` `test_clear_league` and its mutation ("clearing the league
  keeps my team's mark") via `python3 -m unittest tests.test_v2_league_units`: pass, and
  the mutation is caught.
- `python3 -m unittest tests.test_v2_waterfall tests.test_v2_compare`: pass.
- Every module in the `make test-core` list run one by one: all pass except modules that
  launch Chromium, which error at browser launch (no browser here), none on an assertion.

### Claimed, not confirmed

- Render tests (Playwright) were updated for the empty start but not run here: Chromium
  cannot be downloaded in this environment. CI runs them.
- `make validate` could not run locally for the same reason (`make sync` needs Chromium).
- Phone-width screenshots were not taken; the cloud browser does not go below 1024 px.
