## 2026-10-30 - JEG-1130 slice 4: approved copy outside the locked files

Contract: apply the remaining approved PMM copy that sits outside the locked files (v2.js and shell.html,
held by JEG-1137 and JEG-1263) and the hot files (curve-widget.js, value-model.js). Copy only: no value,
default, ranking or behavior change. Jeremy instructed this ("continue parallelizing moving tasks forward in
the linear board", Oct 30 2:57 PM CT).

### What changed
- `app/v2/overrides.js`: "our methodology" and "our value" retired in every user-visible string (the
  Overrides badge tooltip, the Reset aria-label, "Back to ...", the shared-link "Use ..." button, the first
  preset, the basis notes and fallback warnings, the link note, the card intro). The wording is
  "the default DDF Value", as #1185 used in v2.js; the intro now reads "What DDF Value means on every tab.
  The default DDF Value is rooted in the trade charts, then adjusted for position weight and your league's
  rosters, equal weight." Generic "his value" is now "this player's value".
- Generic player as "this player" / "they", never "he" (Jeremy, 2026-10-29 9:21 PM CT, audit decision 10,
  on JEG-1130): the player-search empty state in `league.js`, `waivers.js` and `finder.js` (PMM 3.3's
  "Can't find ..." row, with the new pronoun rule), the league levels note in `league.js`, the Waivers legend,
  two audit glossary rows in `audit-pie.js`, and the values explainer prose in
  `app/values-explainer/template.html` (not a logic file, so no review flag).
- `audit-pie.js` DDF Value glossary row: "Our value:" is now "The default:". It is an audit page, so its
  publisher names stay.
- Tests: new `tests/test_jeg1130_settings_copy.py` (fails on main with 34 findings; 10 mutants each fail),
  wired into `test-unit-modules`. `tests/test_v2_overrides_basis_render.py` pins follow the new preset label
  "Default DDF Value" (the rule they pin changed with the approved glossary).

### Kept on purpose
- "Value basis" (the Overrides card title and the radiogroup label): the newer JEG-1140 Settings components
  (`settings-fieldnotes.js`, merged #1129) use "Value basis", so this slice doesn't roll it back.
- "Your value" for a reader's own override: that is the reader's number, not a retired name for DDF Value.
- "The trade chart average" in Overrides: JEG-1212 term, pinned by JEG-1234.

### Follow-up: League "Your team" / "Your fit" (Jeremy, 2026-10-30 6:29 PM CT, answer A)
- `app/v2/league.js`: the reader's side is "Your team" / "Your fit", matching "Their team" / "Their fit" and the
  rest of the site: the team summary fieldset and filter option, the filter rule line, the summary column labels
  ("Your <field>"), the "Your team fit" table head and the phone card's "Your fit:" line. Copy only.
- Pins follow: `tests/test_v2_league_tables_render.py` (OPP_HEADERS) and `tests/test_v2_league_phone_render.py`
  (the card line check and its mutant). `tests/test_jeg1130_settings_copy.py` now retires "Our team" / "Our fit"
  and a bare "Our" in League (5 new mutants; main's league.js gives 6 findings).
- Not run here: both League render suites (no Playwright in this container); CI `v2-render` runs them.

### Left for later (locked or hot files)
- `v2.js` (locked): the phone legend "Solid = DDA" / "Dashed = rescaled", the "Our names" popover title, the
  Trade targets "Our value" column head, `METHOD_FULL` "Our Data Driven Adjustments", "Our composite", and
  "price him" in the runtime footnote.
- `shell.html` (locked): the Trade targets intro ("against our values") and footnote ("market consensus",
  "our value", "price him").
- `curve-widget.js` (hot): `basisLabelOf` "our methodology" / "Our methodology", the custom-basis note, and
  "doesn't list him". `value-model.js` (hot): two "doesn't list him" estimate notes.
- `values-fieldnotes.js` (JEG-1265 is active on it): "DDF Value is our value:".

### Verified (check named)
- `python3 -m unittest tests.test_jeg1130_settings_copy`: OK; the same check on the main versions of the
  six files reports 34 findings.
- `tests.test_jeg1130_copy_glossary`, `test_jeg1130_v2_copy`, `test_v2_copy_names`,
  `test_launch_copy_guard` (platform-claim grep clean), `test_public_copy_no_vorp`,
  `test_jeg1140_settings_fieldnotes`: 43 run, OK, 4 skipped (browser).
- `node --check` passes on the five edited scripts.

### Claimed, not confirmed
- Render suites need Playwright Chromium, which this cloud container can't download:
  `test_v2_overrides_basis_render` (its re-pinned preset label), and the screenshots. They go to CI
  `v2-render` / the Mac lane.
