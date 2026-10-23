## 2026-10-23 - JEG-947 mobile phase 1 (part of JEG-927)

Scope: scrolling tables with pinned name column and edge fade (Jeremy decision B1, 2026-10-23), 44 px tap targets, hover rules
under `@media (hover: hover)` with touch equivalents, 12 px minimum body text on phones. Chart and nav untouched (later phases).
Changes: `app/v2/v2.css` (touch rules apply below 768 px and on coarse pointers; desktop rules unchanged),
`tests/test_v2_mobile_phase1_render.py` (new). Merged origin/main (plain merge, no conflicts).

### Verified (named checks)
- `tests.test_v2_mobile_phase1_render.test_phase1_guards_hold`: OK before and after the merge (overflow at 320/360/390, scroll container + sticky first column + fade cue, 44 px hit areas incl. 844x390, no unguarded :hover, 12 px text, desktop 1366/1280/1024 unaffected).
- `test_guard_fails_on_broken_builds`: OK; 11 simulated broken builds each reported an error.
- Screenshots 390/360/320 and 1366x768 in `~/code/fantasy-tools-selfhost-notes/mobile-phase1/`.

### Not verified
- Real-phone behavior (iOS Safari sticky + mask, momentum scroll). Chromium emulation only.
- Full `make validate` not run (value lanes in flux; only the new render file run).
- CSS scroll-driven fade needs `animation-timeline`; browsers without it show no fade (table still scrolls).
- Name column is narrow when pinned, so long names clip at 390 px.

### Addendum: "Last, First" names in the pinned column (Jeremy decision, 2026-10-23)
Changes: `app/v2/name-format.js` (new pure `DDFNameFormat.lastFirst(name, pos)`: suffix Jr./Sr./II/III/IV/V stays with the last name,
particles after the first name start a multi-word last name (St., De, Van, Von, Di, Du, ...), one-word names, "Chris Jr.", names
with a comma and DST/DEF pos unchanged), `app/v2/v2.js` (`nameSpan` in the Values and Targets name cells; text swaps with the
phone/touch media query; capture-phase tap handler shows the full name in `.v2-nm-pop`), `app/v2/v2.css` (clip with ellipsis),
`pipelines/build_v2_page.py` (script tag + copy), `Makefile` (node unit test), `tests/test_v2_name_format.js` (new),
`tests/test_v2_mobile_phase1_render.py` (new "names" check + 3 broken-build mutations).
Behavior: phones and coarse pointers show "Harrison Jr., Marvin"; desktop keeps "First Last". `title` carries the full name (hover on desktop).
On touch, tapping a CLIPPED name shows the full name in a popover and does not open the drawer; tapping anywhere else in the row
(sub-line, any other cell) opens the drawer as before. Unclipped names open the drawer on tap, as before.
Scope note: at 390 px the Targets view is the card layout (not a pinned table), so cards keep "First Last"; the Targets table
(landscape phones / touch tablets, 768 px and up) uses the new format.
#### Verified (named checks)
- `node tests/test_v2_name_format.js`: 29 table cases incl. Jr./Sr./II/III/IV/V, St. Brown, De Jesus, Van Vooren, first name "Van", Smith-Njigba, Dont'e Thornton Jr., O'Connell, one-word and DST unchanged; negatives: removing SUFFIX_RE or PARTICLE_RE makes the suffix/particle rows fail. The table found one real bug while writing it ("Chris Jr." became "Jr., Chris"); fixed in the code, not the test.
- Real-data pass over the 1,163 engine players: names with St./Van/De/Le/apostrophes format as expected (spot-checked in the 390 and 844x390 screenshots).
- Screenshots in `~/code/fantasy-tools-selfhost-notes/mobile-phase1/` (`*-names-*`): 390 Values, 390 tap popover, 844x390 Targets table, 1366 unchanged.
- `tests.test_v2_mobile_phase1_render` `test_phase1_guards_hold` with the new "names" check (390 Values text, title, ellipsis clip, tap popover without opening the drawer, 844x390 Targets table, desktop 1366/1280/1024 untouched): OK.
- `test_guard_fails_on_broken_builds`: OK with 3 new mutations (names left First Last, suffix handling removed, clipping removed) each reported an error.
- `tests.test_build_v2_page`: OK.
#### Not verified
- Real-phone tap behavior (Chromium touch emulation only); `make validate` not run (value lanes in flux).
- Decision for Jeremy: a tap on a clipped name shows the popover and does not open the drawer (tap elsewhere on the row still does). The alternative is popover plus drawer together.
- After the second plain merge of origin/main (no conflicts): `test_phase1_guards_hold` OK and `node tests/test_v2_name_format.js` OK again.

### Addendum 2: contract PV-03 failed at c46f0b1 (names read back empty)
Cause: test reader, not a page bug. The contract's `own()` helper reads only the direct text nodes of a name cell; the cell text now lives in a `.v2-nm` span (names are present and visible, "Last, First" on phones). Fix: `own()` returns the span's `data-full` (the full "First Last" name) when the cell has a `.v2-nm`. The PV-03 assertion is unchanged (still requires the zoomed rows to be named in the chart labels), so it still fails if names are really empty.
Verified: `tests.test_v2_contract_render` (6 tests, including its broken-build discrimination run) OK; `test_v2_values_tab_ux_render`, `test_v2_states_render`, `test_v2_targets_render` each run alone, OK. Plain merge of origin/main (#852, #854, #855), no conflicts. Not separately re-proved: a dedicated empty-name mutation for PV-03 (the file's existing broken-build run is the guard).
