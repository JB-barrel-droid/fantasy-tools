## 2026-10-29 - Trade targets in Fieldnotes (JEG-1139, PR #1167)

Contract: put Trade targets into the approved Fieldnotes language behind `?design=fieldnotes`, reusing JEG-1138's value
view and disclosure styling, without changing markup, copy, target signals, QB treatment, thresholds or numbers.

### Verified (check named)
- Trade targets' text is identical with and without the flag at 390 and 1280 px, with the lists closed and with the
  sell list opened: `tests.test_v2_fieldnotes_targets_render` (3 OK, local Mac, system Chrome).
- Keyboard: Show more and Show top 5, a row's per-chart toggle (1280), a weight group's toggle and "How to use it" all
  work with Enter and a 3 px ring. At 390, a tap on a card opens the player. Same test.
- No sideways scroll, all controls at least 44 px (it caught 15 px chart links in opened rows, now fixed), and text
  contrast passes. Same test.
- The unflagged page's computed styles are unchanged without either Fieldnotes block. The guards fail without the
  JEG-1139 block and without the JEG-1138 shared lists. Same test.
- `test_v2_targets_render` fails with output identical to `main` `d67848c9` (the "Rescaled values" popover text), so
  it's pre-existing.

### Claimed, not confirmed
- Safari, physical phones and screen readers; CI's bundled Chromium; `make validate`.
