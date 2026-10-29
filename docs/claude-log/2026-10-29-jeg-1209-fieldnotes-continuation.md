## 2026-10-29 - Fieldnotes revision 3: Find a trade with the sibling components (JEG-1209)

Contract: JEG-1209 acceptance (runnable desktop and phone preview, screenshots with revision and widths, keyboard/focus/disclosure checks, empty/loading/missing states, current-vs-proposed flow, handoffs into JEG-1137 to JEG-1140). Continues Codex's revision-2 handoff #1089 without changing it. Private review only; Jeremy approves the design language before rollout.

Changes: new `preview/jeg-1209-fieldnotes/` (build script, browser checks, `src/`, pinned `vendor/` copies of JEG-1233 #1091, JEG-1231 #1090, JEG-1232 #1093, JEG-1217 #1084 and main's `workspace.js` / `opportunities.js`, built `index.html`), `docs/design/jeg-1209-fieldnotes/continuation/` (brief, verification), `.github/workflows/jeg1209-preview.yml` (build check, browser checks, screenshot artifact; preview paths only). No file under `app/` changes.

### Verified (check named)
- See `docs/design/jeg-1209-fieldnotes/continuation/verification.md`: `build.py --check`, a jsdom smoke run of the built page, and the three workflow tests (35 pass).

### Claimed, not confirmed
- Browser checks and screenshots run only in CI (no Chromium download in the sandbox).
- The JEG-1232 and JEG-1233 concept pages still use the older `concept.css` palette; their components draw in Fieldnotes here through token mapping, not by changing them.
