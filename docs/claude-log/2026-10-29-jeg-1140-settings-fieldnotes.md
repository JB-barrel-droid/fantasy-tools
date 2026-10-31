## 2026-10-29 - JEG-1140 Settings and local data in the Fieldnotes design (isolated components)

Contract: build Settings and the local-data presentation as isolated components in the JEG-1209 Fieldnotes design, on the
JEG-1137 foundation layer already on main (tokens and `.ddf-fn-*` controls). Keep the Export, Import, Copy link, override
and selected-league entry contracts unchanged; no new storage, valuation engine, math, default or ranking change. Final
runtime integration (route, nav, shell) is held until the JEG-1137 shell lands with its owner. No existing runtime file is
edited.

New files:
- `app/v2/settings-fieldnotes.js`: `TradeValueSettingsFieldnotes = {viewModel, render, mount, liveAdapter, settingsFromQuery, rulesText, STRINGS}`.
  Pure view model, a renderer, a mount with one stable `role=status` region, and `liveAdapter(window)`, which reads
  `TradeValueWorkspace.store`, `TradeValueV2.leagueQuery()` and `DDFOverrides` and only presses the existing controls
  (`#v2LgDownload`, `#v2LgLoad`, `#v2LgCopyLink`, `#v2OvExport`, `#v2OvImport`) or sets the existing routes
  (`#find-league`, `#value-overrides`). Every string is in one table (`STRINGS`) so the JEG-1130 copy lane can change it in one place.
- `app/v2/settings-fieldnotes.css`: layout only, every rule under `:root[data-design="fieldnotes"]`.
- `tests/settings_fieldnotes_logic.cjs`, `tests/test_jeg1140_settings_fieldnotes.py`: node checks (no browser).
- `tests/test_jeg1140_settings_fieldnotes_render.py`: harness and built-page browser tests.
- `tests/fixtures/settings-fieldnotes/`: synthetic league, overrides and context states.
- `.github/workflows/jeg1140-settings-render.yml`: runs both modules on PRs that touch them and uploads the screenshots.
- `Makefile`: the two modules added to `test-unit-modules` (tests/test_render_sweep_coverage.py needs every render module wired).

### Verified (check named)

- `python3 -m unittest tests.test_jeg1140_settings_fieldnotes`: 14 passed locally. Covers every fixture state (loading,
  error, ready, custom basis, no team, empty, missing, unavailable, storage full, long names); unknown counts and
  settings read "Unavailable", never 0; JEG-1212 terms; no publisher names or account/sync claims; the league file
  round-trips through `exportJson`/`importJson` unchanged and twice; the league link reopens the same teams, keys and the
  kicker's exact identity read the way league.js reads it; over the link budget only "my team" travels.
- Mutation check: making the rules row read "0 teams" and always showing the player count made
  `test_missing_counts_and_settings_are_unavailable_never_zero` fail; restored.
- No existing runtime file changed (`git diff origin/main --stat` lists only new files plus the Makefile lines).

### Claimed, not confirmed

- The browser tests (`tests.test_jeg1140_settings_fieldnotes_render`) skip locally: this container cannot download
  Chromium. They run in CI (new workflow, and test-unit-modules in the full suite) with `RENDER_TESTS_REQUIRED=1`. Their
  first CI result is the evidence for 320/390/1280 and dark, keyboard and focus, and the built-page round-trip by file and
  link through the existing controls.
- Held for after JEG-1137 lands (its owner on Jeremy's Mac): the Settings route and nav entry in `shell.html`/`v2.js`, the
  appearance toggle and "View settings" button, and any shared-control hunk.

### Follow-up: first CI run (settings-render, head 4d96d1b)

- Verified from the CI log: the keyboard/focus and section-link harness tests passed; the node checks passed (14).
- Red, fixed: the Copy link button's name "Copy league link" did not contain its visible label "Copy link" (WCAG 2.5.3),
  in every state and width. Renamed to "Copy link to this league"; a node assertion that every action name starts with its
  label now fails on the old name (checked) and passes.
- Red, fixed (test scaffolding): the built-page tests mounted their host as a direct child of body, which v2.css hides
  (`body.v2 > :not(.v2-app)`), so no button was visible. The host now goes inside `.v2-app`. Not confirmed until CI reruns.
- Red, fixed (preview-shard 1, head 670b9fe): `tests.test_v2_copy_names` (JEG-1081) bars the retired name "DDF Projections"
  from every user-visible string in app/v2. The projections view is "DDF Value (projections)" (Jeremy's pick C, Oct 28,
  and the finder's own label), so Settings now uses it. `tests.test_v2_copy_names` and the JEG-1140 node checks pass locally.

### JEG-1306 corrections (independent Claude review of 670b9fe3)

Verified (local, node and Python; checked by running the new tests against the pre-fix file, then the fix):
- Finding 1: `tests.test_launch_copy_guard` failed 1 of 4 on "in this browser" before; passes after ("Saved on this device.").
- Finding 2: the Overrides import wait now follows the input this press created (the tab leaves cancelled inputs behind),
  each action has its own pending flag, and a window-focus fallback ends a wait where the browser sends no cancel event.
  Found while writing the test: a cancel set a flag but nothing re-ran the wait's check (a cancel changes no DOM), so
  every cancelled import waited out its 120 s. waitFor now takes a wake hook and the cancel re-runs the check.
  Fake-page node tests fail before (both waits hang; no focus fallback) and pass after.
- P3 folded in: a replace prompt showing before the press is ignored (new first child = new prompt); a load is a success
  when the notice ends "loaded." (a league named "Not Bad" no longer reads as an error); Export overrides is on with a
  custom basis and no overrides; status text is written on the next task; workflow path filter widened.
- `tests.test_jeg1140_settings_fieldnotes` (19), `tests.test_launch_copy_guard`, `tests.test_v2_copy_names` pass.

Claimed, not confirmed:
- New browser tests (pending picker blocks only its own button; two cancelled overrides imports on the built page) run in
  CI only; their fail-before is shown by the node tests above, not in a browser.
- Left for integration (noted on JEG-1140): a public ready() for overrides, a store onChange hook, unique ids on a second mount.
