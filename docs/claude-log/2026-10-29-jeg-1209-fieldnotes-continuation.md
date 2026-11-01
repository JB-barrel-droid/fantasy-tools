## 2026-10-29 - Fieldnotes revision 3: Find a trade with the sibling components (JEG-1209)

Contract: JEG-1209 acceptance (runnable desktop and phone preview, screenshots with revision and widths, keyboard/focus/disclosure checks, empty/loading/missing states, current-vs-proposed flow, handoffs into JEG-1137 to JEG-1140). Continues Codex's revision-2 handoff #1089 without changing it. Private review only; Jeremy approves the design language before rollout.

Changes: new `preview/jeg-1209-fieldnotes/` (build script, browser checks, `src/`, pinned `vendor/` copies of JEG-1233 #1091, JEG-1231 #1090, JEG-1232 #1093, JEG-1217 #1084 and main's `workspace.js` / `opportunities.js`, built `index.html`), `docs/design/jeg-1209-fieldnotes/continuation/` (brief, verification), `.github/workflows/jeg1209-preview.yml` (build check, browser checks, screenshot artifact; preview paths only). No file under `app/` changes.

### Verified (check named)
- See `docs/design/jeg-1209-fieldnotes/continuation/verification.md`: `build.py --check`, a jsdom smoke run of the built page, and the three workflow tests (35 pass).

### Claimed, not confirmed
- Browser checks and screenshots run only in CI (no Chromium download in the sandbox).
- The JEG-1232 and JEG-1233 concept pages still use the older `concept.css` palette; their components draw in Fieldnotes here through token mapping, not by changing them.

### Update: no free text inputs
Jeremy, 2026-10-29, approving Fieldnotes with changes: "Make it, and no free text inputs". `build.py` now applies `NO_FREE_TEXT` (exact replacements, each must match once) to the pinned revision-2 page and to `manager-profiles-ui.js`, and writes `revision2.html`; the pinned sources are unchanged. Replacements and checks are listed in `continuation/brief.md` and `continuation/verification.md`. The production note field in #1084 (JEG-1217) still has a text box until that PR follows the rule.

Narrowed the same day. Jeremy: "I just didn't want text boxes for how my leaguemates trade, and set everyone to default initially." `NO_FREE_TEXT` now changes only the Managers note (checkboxes) in the pinned #1084 copy; the revision-2 inputs are back as revision 3 had them, and `revision2.html` differs from the prototype only in its Find a trade route. `checks.py` checks the Managers card for text boxes and that every manager starts at the default profile.

## JEG-1250 corrections (2026-10-29, Claude)

Review e1e9a3b2 / a284ed4d, CHANGES REQUIRED at `840cd4e1`. Fixed on this branch:
- Storage: both stores on preview-only keys (`build.py` `PREVIEW_STORAGE`); sample league seeded only when absent or on Reset preview; filters and profiles persist through reload and No league.
- Announcements: one `#previewLive` region outside rerendered controls; focus kept on the pressed control.
- Legacy note: ticked boxes lead, earlier text kept verbatim, over-length ticks refused.
- Pins: #1090 to `a5471429`; column-order dropped (Jeremy's fixed order, #1093 `b7e076f8`); open findings for #1091 and #1084 in `MANIFEST.json` and the brief; JEG-1230 readout and JEG-1229 preferences relabelled as planned.
Checks: `checks.py` 140/140 locally; the same checks fail 19 at `840cd4e1`.
Second delta (review 38ed85e1): Managers ticks moved to a preview-only key so no note is rewritten or parsed as ticks; column-order copies restored and pinned as not loaded (no file deletion on the branch). `checks.py` 148/148; the new legacy checks fail 12 at `82dcb092`.
Decisions recorded on JEG-1209 (Jeremy, 2026-10-29): Fieldnotes as shown ("so A"); Values and AI path as separate scopes via Codex; JEG-1141 matches Fieldnotes motion.
