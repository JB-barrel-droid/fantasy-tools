## 2026-10-29 - JEG-1231 opponent inclusion checkboxes (component lane)

Contract: an isolated, stable-ID opponent inclusion helper and accessible checkbox component for the league-wide trade
search, a private preview drawn in the JEG-1209 tokens, and tests. No league.js, finder.js, workspace.js, value, fit or
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
- The preview page's logic in jsdom (scratch only, not committed): counts, rename, re-add, Select all / Clear all,
  won't-trade lock, duplicates and the empty state behave as the render test expects.

### Claimed, not confirmed
- `tests/test_jeg1231_opponent_inclusion_render.py` (keyboard order, Space toggling, focus kept after redraw, 44px targets,
  one column and no sideways scroll at 390) has not run here: this container has no Chromium. It runs in the v2 render
  workflow on the PR.
- Screenshots at 1280 and 390, light and dark, come from that CI run's artifact, not from this session.
- The exact Fieldnotes preview revision was not found in GitHub; the control uses the Oct 26 direction tokens
  (`app/v2-concept/concept.css`) through CSS variables with fallbacks. Asked the release coordinator on JEG-1231 for the link.
