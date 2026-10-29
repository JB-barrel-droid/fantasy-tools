## 2026-10-29 - JEG-1231 opponent inclusion checkboxes (component lane)

Contract: an isolated, stable-ID opponent inclusion helper and accessible checkbox component for the league-wide trade
search, a private preview drawn in the JEG-1209 Fieldnotes direction, and tests. No league.js, finder.js, workspace.js, value, fit or
ranking change in this PR; the league hookup is a separate PR after #1072.

New paths: `app/v2/opponent-inclusion.js`, `app/v2/opponent-inclusion.css`, `preview/opponent-inclusion/index.html`,
`tests/node/opponent_inclusion_check.cjs`, `tests/test_jeg1231_opponent_inclusion.py`,
`tests/test_jeg1231_opponent_inclusion_render.py`. Registered in `make test-unit-modules`, `test-render-sweep-3` and the
v2 render workflow (which uploads the review screenshots as the `jeg-1231-opponent-inclusion-shots` artifact).

Picks (logged in the picks log): today's baseline is kept, every opponent is searched until the reader leaves one out, so
only exclusions are stored (`ws.ui.opponentInclusion = {v: 1, excluded: [teamId]}`, the existing workspace store). A new or
re-added team (new id) arrives included. A JEG-1217 "won't trade" profile is read through a predicate and stays out: the
box is unticked, focusable, `aria-disabled`, and says the choice lives in Managers. Repeated names get "team N".

### Verified (check named)
- `python3 -m unittest tests.test_jeg1231_opponent_inclusion`: 12 checks pass on the real workspace.js, opportunities.js and
  finder.js with the 4-team fixture, and each of 6 mutations is caught by its named check.
- Excluding a team removes its offers; the remaining rows are identical to the full run apart from list position, every
  remaining pairing is reused from the cache (`computed` 0), and a cold run agrees
  (`test_search_excludes_offers_without_changing_values`).
- Rename keeps the choice, removal drops the id, a same-name team added back arrives included, duplicates stay apart,
  star moves, no opponents, all excluded, and the state survives `W.serialize`/`W.parseStored` (named tests in the harness).
- The preview page's logic in jsdom (scratch only, not committed): counts, rename, re-add, Select all / Clear,
  won't-trade lock, duplicates and the empty state behave as the render test expects.

### Claimed, not confirmed
- `tests/test_jeg1231_opponent_inclusion_render.py` (keyboard order, Space toggling, focus kept after redraw, 44px targets,
  one column and no sideways scroll at 390) has not run here: this container has no Chromium. It runs in the v2 render
  workflow on the PR.
- Screenshots at 1280 and 390, light and dark, come from that CI run's artifact, not from this session.

### Fieldnotes alignment (correction)
An earlier note on this PR and on JEG-1231 said no Fieldnotes artifact had been provided. That was wrong: it was in
#1089, handed off at `docs/design/jeg-1209-fieldnotes/` (pinned at `2c8931231ccd2bbeb4946ac031aee5ac655182f4`, revision 2,
with `acceptance-amendment.md`). Reconciled against that baseline and amendment:
- Labels follow the prototype's Filters panel: "Opponents to include", "Select all" and "Clear" (Clear means none). Each row
  shows its team's player count as the prototype does, from `playerCount` when the caller supplies one.
- The amendment's opponent-inclusion terms hold: stable team IDs, default all, explicit Select all/Clear, deleted teams
  dropped, my own team never listed.
- CSS fallbacks are the Fieldnotes light roles (canvas #F5F2EA, surface #FFFDF8, ink #182D27, line #D4D8CD, control #79897F,
  action #126044, focus #175BC1 as a 3px outline), 9px control radius, 44px controls, 48px rows, 160ms motion. The
  `--ddf-*` tokens still come first, so the public league page keeps today's palette until the shell rollout (JEG-1137).
- The preview page now sets the Fieldnotes light and dark roles copied from `prototype.html` instead of loading the
  Oct 26 concept stylesheet.
- Verified here: the Node harness and mutations (now 7) pass, and the preview's labels and counts check out in jsdom
  (scratch only). The browser render tests and screenshots for this head come from CI.
- Not adopted from the prototype: it puts the control inside a Filters modal; placement on the league page belongs to
  the hookup PR and the redesign owners.
