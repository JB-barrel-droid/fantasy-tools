# 2026-10-29 - JEG-1236 league phone target sizes (Claude)

Base: main `5ec64d2`. Branch `claude/JEG-1236-phone-target-hit-area`. Test-only change: `tests/test_v2_league_phone_render.py`.
No runtime, CSS, value, default or methodology change.

## What failed and why

Coordinator's Mac sweep on `dbe06a7e`: `test_phone_contrast_keyboard` reported inputs at 20x20 at 390, 360 and 320 px. The error
list is cut to six entries, so six is the display cap, not the count. The inputs are the "Add team summary columns" checkboxes
(`input[data-summary-column]`, league.js `summaryControls`, two fieldsets: Our team and Their team). CSS (v2.css
`.v2-lg-field-options`) draws each box at 20 px inside a `label { display: flex; min-height: 44px }` that wraps it, so the
label is the implicit association and, by HTML label activation, the whole label toggles the box.

The old check measured only the control's own box. It also measured closed-fold content only when the browser lays it out
(newer Chromium does for closed `<details>`), which is why the boxes showed up on the Mac and not before.

Conclusion: test drift, not a runtime regression, provided the label really takes the tap. The new check proves that rather
than assuming it from geometry.

## The new assertion (keeps the 44 px requirement)

- Size: every control in the three league boxes is measured with every closed fold opened (and closed again after). A checkbox
  or radio under 44 px passes only when it has an associated label of at least 44 x 44 px. No label: it fails as before.
- Hit test (every labelled box): `elementFromPoint` 2 px inside each label corner must land on the label or the box.
- Pointer activation (each fieldset's first and last box, each width): a real mouse click at each label corner must toggle
  the box; four clicks restore it. Each click saves and redraws the workspace, so clicks are sampled; the hit test covers all.
- Keyboard and name: the box takes focus, is named by its label (accessible role query), and Space toggles it and restores it.
- Viewport, fixture and the 43.5 px threshold are unchanged.

## Mutations added to test_guard_fails_on_broken_builds

- the summary column checkbox loses its label (label -> span): phone check reports `controls under 44px`
- the label min-height 44 -> 24: phone check reports `through its label`
- the label gets `pointer-events: none` (size unchanged): labels check reports `label edge`, so geometry alone cannot pass

## Evidence and what is still to run

- This cloud container cannot download a Playwright browser (CDN blocked), so the browser checks were not run here.
- The page scripts were syntax-checked with node and exercised in jsdom with stubbed geometry: 44 px label passes,
  24 px label and label-less box fail with the expected messages, a covered edge fails the hit test, folds are restored.
- Still required: the focused module on a real browser, `python3 -m unittest tests.test_v2_league_phone_render`
  (both tests, including the mutation guard), at the release coordinator's Mac, plus screenshots at 390 and 320 px.

## Round 2, after the Mac run on 24c9f19 (both tests ran, guard PASS, phone check FAIL)

Codex's Mac run found two real problems; both fixed here.

1. Real UI defect: `#v2LgSummaryFilterValue` (the "Filter by team summary" value box) drew 162x26 at 390/360/320. Fix, one
   scoped line in v2.css, posted on JEG-1236 first: `.v2-lg-field-options .v2-field input[type="text"] { min-height: 44px; }`.
   Height only, only inside the league summary folds. Overlap: of the open UI PRs only #1069 touches v2.css (hunks near 2007 and
   2260); this line is next to the existing checkbox rule near 2203. New mutation: drop the line, and the phone check must name
   "Summary filter value".
2. Test timing defect: the page sets `html { scroll-behavior: smooth }`, so LABEL_BOX and CORNERS read the label box while the
   scroll was still moving. Both now scroll with `behavior: 'instant'` after opening the folds, and require the label to be
   wholly in the viewport before any hit test, click or keyboard check, with a "not in view" diagnostic otherwise.
3. From the independent review: radios are expected only to turn on (no toggle-off), and disabled or aria-disabled boxes are
   still measured and hit-tested but not activation-toggled.

Verified here: compile, node parse, jsdom (in-view and off-screen cases). Still needs the coordinator's two-test browser rerun.
