## 2026-10-30 - JEG-1140 How values work in the Fieldnotes design

Contract: put the explainer frame in the approved Fieldnotes design (JEG-1209) behind the existing flag, without touching
`v2.js` or `shell.html` (locked by JEG-1137 and JEG-1263). No value, number, copy or storage change. Merged origin/main
into the branch (one add/add conflict in the render test; main's version taken, it contains both branch hunks).

### Verified (check named)
- `tests.test_jeg1140_explainer_fieldnotes_render` (5 tests, Chrome): with the flag the frame's panel color equals the
  parent's `--ddf-surface` in light and dark at 1280 and 390, no sideways scroll, controls at least 44 px, Fraunces named
  for headings, 3 px focus ring, follows a parent theme switch, unchanged without the flag. Run against main's template it
  fails (6 failures); with the change it passes.
- Dark failed first: the frame's own dark rule outranked the Fieldnotes variables; fixed with `:root` specificity.

### Claimed, not confirmed
- The frame falls back to Georgia for headings (the Fraunces face is declared once, in the dashboard).
- Waiting on locks: Settings route, nav entry, appearance toggle, "View settings" button.

### Corrections from independent review (2026-10-30)

- Workflow: moved `test_jeg1140_explainer_fieldnotes_render` step below the `env: SETTINGS_FIELDNOTES_SHOTS` block so the settings screenshots continue to save.
- HANDOFF.md: merged origin/main normally; kept both sides (JEG-1385 and JEG-1140 entries).
- Docstring: updated to match what `test_guard_fails_without_the_rules` actually does (static text assertions, no browser).
- `test_frame_follows_a_theme_switch`: replaced assertNotEqual with assertEqual(framePanelBg, parentDarkSurface). Verified: fails on main's template, passes with the change.
